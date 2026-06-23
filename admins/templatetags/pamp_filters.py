from django import template

register = template.Library()


@register.filter
def split(value, sep=' '):
    return value.split(sep)


@register.filter
def get_item(dictionary, key):
    """Look up a dict value by a dynamic key: {{ my_dict|get_item:variable }}"""
    return dictionary.get(key)
