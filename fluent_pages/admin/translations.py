"""
Translation support for admin forms.
"""
from django import forms


def get_model_form_field(model, name, **kwargs):
    return model._meta.get_field_by_name(name)[0].formfield(**kwargs)


class TranslatableModelFormMixin(object):
    """
    Form mixin, to fetch+store translated fields.
    """
    _translatable_model = None
    _translatable_fields = ()

    language_code = forms.CharField(max_length=15, widget=forms.HiddenInput)


    def __init__(self, *args, **kwargs):
        super(TranslatableModelFormMixin, self).__init__(*args, **kwargs)

        # Load the initial values for the translated fields
        instance = kwargs.get('instance', None)
        if instance:
            for field in self._translatable_fields:
                self.initial.setdefault(field, getattr(instance, field))


    def save(self, commit=True):
        # Assign translated fields to the model (using the TranslatedAttribute descriptor)
        for field in self._translatable_fields:
            setattr(self.instance, field, self.cleaned_data[field])

        return super(TranslatableModelFormMixin, self).save(commit)
