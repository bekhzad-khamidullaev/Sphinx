from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
import logging
from checklists.models import Location

from .models import QRCodeLink, Review
from .forms import ReviewForm

logger = logging.getLogger(__name__)

class SubmitReviewView(View):
    template_name = 'qrfikr/submit_review.html'
    form_class = ReviewForm

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def get(self, request, qr_uuid):
        qr_link = get_object_or_404(QRCodeLink.objects.select_related('location'), id=qr_uuid, is_active=True)
        form = self.form_class()
        page_title = _("Leave Feedback for %s") % (qr_link.location.name if qr_link.location else _("this Location"))
        location_description = qr_link.short_description or (qr_link.location.name if qr_link.location else '')
        
        context = {
            'qr_link': qr_link,
            'location': qr_link.location,
            'form': form,
            'page_title': page_title,
            'location_description': location_description,
        }
        return render(request, self.template_name, context)

    def post(self, request, qr_uuid):
        qr_link = get_object_or_404(QRCodeLink.objects.select_related('location'), id=qr_uuid, is_active=True)
        form = self.form_class(request.POST, request.FILES)
        page_title = _("Leave Feedback for %s") % (qr_link.location.name if qr_link.location else _("this Location"))
        location_description = qr_link.short_description or (qr_link.location.name if qr_link.location else '')

        if form.is_valid():
            try:
                review = form.save(commit=False)
                review.qr_code_link = qr_link
                review.ip_address = self.get_client_ip(request)
                review.user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
                review.save()
                
                logger.info(f"Review {review.id} submitted for QR {qr_uuid} from IP {review.ip_address}")
                messages.success(request, _("Thank you for your feedback! It has been successfully submitted."))
                return redirect(reverse('qrfikr:submit_review_thank_you', kwargs={'qr_uuid': qr_uuid}))
            except Exception as e:
                logger.exception(f"Error saving review for QR {qr_uuid}: {e}")
                messages.error(request, _("An error occurred while submitting your feedback. Please try again later."))
        else:
            logger.warning(f"Invalid review form for QR {qr_uuid}: {form.errors.as_json()}")

        context = {
            'qr_link': qr_link,
            'location': qr_link.location,
            'form': form,
            'page_title': page_title,
            'location_description': location_description,
        }
        return render(request, self.template_name, context)


class ThankYouView(View):
    template_name = 'qrfikr/thank_you.html'

    def get(self, request, qr_uuid):
        qr_link = get_object_or_404(QRCodeLink.objects.select_related('location'), id=qr_uuid)
        context = {
            'page_title': _("Feedback Submitted"),
            'location_name': qr_link.location.name if qr_link.location else _("the location"),
            'qr_link': qr_link
        }
        return render(request, self.template_name, context)

from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator

@method_decorator(staff_member_required, name='dispatch')
class AdminQRCodeDetailView(View):
    template_name = 'qrfikr/admin_qr_detail.html'

    def get(self, request, pk):
        qr_link = get_object_or_404(QRCodeLink.objects.select_related('location'), pk=pk)
        context = {
            'qr_link': qr_link,
            'title': _("QR Code Details for %s") % (qr_link.location.name if qr_link.location else qr_link.id),
            'opts': QRCodeLink._meta,
            'site_header': getattr(settings, 'ADMIN_SITE_HEADER', _('Django administration')),
            'site_title': getattr(settings, 'ADMIN_SITE_TITLE', _('Django site admin')),
            'has_permission': request.user.is_staff,
        }
        return render(request, self.template_name, context)

class LocationDetailView(DetailView):
    model = Location
    template_name = 'qrfikr/location_detail.html'
    context_object_name = 'location_object'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.object.name
        return context