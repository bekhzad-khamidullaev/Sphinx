from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView, TemplateView, DetailView
from django.urls import reverse
from django.contrib import messages

from .models import QRCodeLink
from .forms import ReviewForm


class SubmitReviewView(FormView):
    template_name = 'qrfikr/submit_review.html'
    form_class = ReviewForm

    def dispatch(self, request, *args, **kwargs):
        self.qr_link = get_object_or_404(QRCodeLink, id=kwargs['qr_uuid'], is_active=True)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        review = form.save(commit=False)
        review.qr_code_link = self.qr_link
        review.ip_address = self.request.META.get('REMOTE_ADDR')
        review.user_agent = self.request.META.get('HTTP_USER_AGENT', '')
        review.save()
        messages.success(self.request, 'Thanks for your feedback!')
        return redirect(reverse('qrfikr:thank_you', kwargs={'qr_uuid': self.qr_link.id}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['qr_link'] = self.qr_link
        return context


class ThankYouView(TemplateView):
    template_name = 'qrfikr/thank_you.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['qr_link'] = get_object_or_404(QRCodeLink, id=self.kwargs['qr_uuid'])
        return context


class LocationDetailView(DetailView):
    template_name = 'qrfikr/location_detail.html'
    model = QRCodeLink
    slug_field = 'id'
    slug_url_kwarg = 'qr_uuid'

