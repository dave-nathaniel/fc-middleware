from rest_framework.response import Response

class APIResponse(Response):
    def __init__(self, message, status, data=None, status_code=None):
        response_data = {
            'message': message,
        }

        if data is not None:
            response_data['data'] = data

        if status in range(200, 299):
            response_data["status"] = "success"
        else:
            response_data["status"] = "failed"

        super().__init__(response_data, status=status_code)