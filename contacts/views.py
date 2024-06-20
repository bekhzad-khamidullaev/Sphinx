from django.shortcuts import render, get_object_or_404
from .models import Contact

def contact_list_view(request):
    account_id = request.GET.get('acc', None)
    contacts = Contact.contact_list_query(account_id=account_id, user=request.user)
    context = {'contacts': contacts}
    return render(request, 'contact_list.html', context)

def contact_detail_view(request, pk):
    contact = get_object_or_404(Contact, id=pk)
    context = {'contact': contact}
    return render(request, 'contact_detail.html', context)
