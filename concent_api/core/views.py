from django.views.decorators.http import require_POST

from utils.api_view import api_view


@api_view
@require_POST
def send(_request):
    return "message received"


@api_view
@require_POST
def receive(_request):
    return "message sent"


@api_view
@require_POST
def receive_out_of_band(_request):
    return HttpResponse("out of band message sent", status = 200)
