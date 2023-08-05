from django.forms import model_to_dict
from django.http.response import JsonResponse
from django.views import View

from demo.models import History


class Some(View):
    async def get(self, request):
        obj = await History.shard("20230803-aaabbb", create=True).objects.afirst()
        return JsonResponse(model_to_dict(obj))
