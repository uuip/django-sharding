# Django 按日期分表实现

1. 定义模型 models.py

```python
from django.db import models
from demo.sharding import ShardingMixin


class History(models.Model, ShardingMixin):
    id = models.BigAutoField(primary_key=True)
    query_time = models.BigIntegerField()
    tag_id = models.CharField(max_length=255, unique=True)

    class Meta:
        abstract = True
        db_table = "history_{}"
```

2. 映射已有模型 apps.py

```python
from django.apps import AppConfig


class DemoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'demo'

    def ready(self):
        from .models import History

        History.discover_models()
```

3. Views  
兼容同步与协程视图

```python
class Some(View):
    async def get(self, request):
        obj = await History.shard("20230803-aaabbb", create=True).objects.afirst()
        return JsonResponse(model_to_dict(obj))
```

4. 关于migrations  
分表的模型会在migrations中生成，但已设置`managed=False`，故不会在migrate时创建表 -- 在步骤3 create=True 时创建。
