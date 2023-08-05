from django.db import models

from demo.sharding import ShardingMixin


class History(models.Model, ShardingMixin):
    id = models.BigAutoField(primary_key=True)
    query_time = models.BigIntegerField()
    tag_id = models.CharField(max_length=255, unique=True)

    class Meta:
        abstract = True
        db_table = "history_{}"
