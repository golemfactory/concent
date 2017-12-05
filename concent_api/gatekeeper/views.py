from base64                         import b64decode

from django.http                    import HttpResponse
from django.views.decorators.http   import require_POST
from django.views.decorators.csrf   import csrf_exempt


@csrf_exempt
@require_POST
def file_transfer_auth(request):
    return HttpResponse("", status=200)
