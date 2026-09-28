from django import template

from accounts.utils import stored_image_url

register = template.Library()


@register.filter
def stored_media_url(file_field):
    return stored_image_url(file_field)
