from django.http import JsonResponse


def gatekeeper_access_denied_response(message):
    data = {'message': message}
    response = JsonResponse(data, status = 401)
    response.WWW_Authenticate = 'Golem realm="Concent Storage"'
    return response
