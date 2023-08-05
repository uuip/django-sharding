import concurrent.futures
from datetime import date
from typing import Self
from warnings import warn

import psycopg
from django.conf import settings
from django.db import connection
from django.db.migrations import operations
from django.db.migrations.migration import Migration
from django.db.migrations.state import ModelState, ProjectState
from psycopg.rows import dict_row

namespace = {}

dbkeys = ["USER", "PASSWORD", "HOST", "PORT", "NAME"]
dsn = "postgresql://{}:{}@{}:{}/{}".format(*[settings.DATABASES["default"].get(k) for k in dbkeys])


def get_create_sql_for_model(model):
    # 生成的表名无论如何都有app_label前缀，也不理会Meta里指定，
    # operation.database_forwards生成fake model，这一步重新生成了db_table；与真是运行migrate不同点在ProjectState
    model_state = ModelState.from_model(model)

    # Create a fake migration with the CreateModel operation
    cm = operations.CreateModel(name=model_state.name, fields=[(k, v) for k, v in model_state.fields.items()])
    migration = Migration("fake_migration", model._meta.app_label)
    migration.operations.append(cm)

    # Let the migration framework think that the project is in an initial state
    state = ProjectState()

    # Get the SQL through the schema_editor bound to the connection
    with connection.schema_editor(collect_sql=True, atomic=migration.atomic) as schema_editor:
        migration.apply(state, schema_editor, collect_sql=True)

    # return the CREATE TABLE statement
    return "\n".join(schema_editor.collected_sql)


class ShardingMixin:
    @classmethod
    def shard(cls, tag_id: str, create: bool = False) -> Self:
        date_prefix = tag_id[:8]
        try:
            d = date.fromisoformat(date_prefix)
            now = date.today()
            if d > now:
                raise
        except:
            raise ValueError("tag_id is illegal data")
        suffix = date_prefix[:6]
        model_name = cls.__name__ + "_{}".format(suffix)
        table_name = f"{cls._meta.app_label}_{cls._meta.db_table}".format(suffix)

        if model := namespace.get(model_name):
            return model

        sql = "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public' AND tablename=%s"
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            rst = conn.execute(sql, [table_name]).fetchone()
        if rst["count"] == 0:
            if create:
                model = cls._create_model_with_table(table_name, model_name)
            else:
                raise ValueError("tag_id is illegal data")
        else:
            warn(f"can not map model to table name {table_name}, now call discover_models", RuntimeWarning)
            cls.discover_models()
            return namespace[model_name]
        return model

    @classmethod
    def discover_models(cls):
        table_name_expr = f"^{cls._meta.app_label}_{cls._meta.db_table}".replace("{}", r"\d+")
        sql = "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ~ %s"
        with connection.cursor() as cursor:
            cursor.execute(sql, [table_name_expr])
            rst = cursor.fetchall()
        for item in rst:
            table_name = item[0]
            suffix = table_name.split("_", 2)[-1]
            model_name = cls.__name__ + "_{}".format(suffix)
            if model_name not in namespace:
                namespace[model_name] = cls._create_model(table_name, model_name)

    @classmethod
    def _create_model(cls, table_name, model_name):
        class Meta:
            managed = False  # 从migrations排除
            # db_table = table_name

        attrs = {
            "__module__": cls.__module__,
            "Meta": Meta,
        }

        model = type(model_name, (cls,), attrs)
        namespace[model_name] = model
        return model

    @classmethod
    def _create_model_with_table(cls, table_name, model_name):
        model = cls._create_model(table_name, model_name)
        # 兼容协程试图
        with concurrent.futures.ThreadPoolExecutor() as executor:
            task = executor.submit(get_create_sql_for_model, model)
        concurrent.futures.wait([task])
        # 生成的sql表明带app_label前缀
        sql = task.result()
        with psycopg.connect(dsn) as conn:
            try:
                conn.execute(sql)
            except psycopg.errors.DuplicateTable:
                pass
        return model
