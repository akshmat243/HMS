from MBP.views import ProtectedModelViewSet
from .models import Account, Transaction
from .serializers import AccountSerializer, TransactionSerializer


class AccountViewSet(ProtectedModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    model_name = 'Account'
    lookup_field = 'slug'


class TransactionViewSet(ProtectedModelViewSet):
    queryset = Transaction.objects.select_related('account').all()
    serializer_class = TransactionSerializer
    model_name = 'Transaction'
