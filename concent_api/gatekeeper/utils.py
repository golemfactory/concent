from django.http import JsonResponse


def gatekeeper_access_denied_response(message, path = None, subtask_id = None, client_key = None):
    data = {
        'message':         message,
        'path_to_file':    path,
        'subtask_id':      subtask_id,
        'client_key':      client_key,
    }
    response = JsonResponse(data, status = 401)
    response.WWW_Authenticate = 'Golem realm="Concent Storage"'
    return response
