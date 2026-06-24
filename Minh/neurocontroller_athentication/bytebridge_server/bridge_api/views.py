from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

class ReflectView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "status": "success",
            "message": "ByteBridge Connected!",
            "user": str(request.user)
        })