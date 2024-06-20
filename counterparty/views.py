from django.shortcuts import render, get_object_or_404
from .models import Counterparty

def counterparty_list_view(request):
    account_id = request.GET.get('acc', None)
    counterpartys = Counterparty.counterparty_list_query(user=request.user)
    context = {'counterpartys': counterpartys}
    return render(request, 'counterparty_list.html', context)

def counterparty_detail_view(request, pk):
    counterparty = get_object_or_404(Counterparty, id=pk)
    context = {'counterparty': counterparty}
    return render(request, 'counterparty_detail.html', context)
