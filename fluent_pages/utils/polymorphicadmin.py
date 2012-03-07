"""
ModelAdmin code to display polymorphic models.

Already made generic.
"""
from django import forms
from django.conf.urls.defaults import patterns, url
from django.contrib import admin
from django.contrib.admin.helpers import AdminForm, AdminErrorList
from django.contrib.admin.widgets import AdminRadioSelect
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import RegexURLResolver
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from django.utils.encoding import force_unicode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
import abc


class PolymorphicModelChoiceAdminForm(forms.Form):
    ct_id = forms.ChoiceField(label=_("Type"), widget=AdminRadioSelect(attrs={'class': 'radiolist'}))


def _dummy_change_view(request, id):
    raise Http404("Dummy page for polymorphic classes")



class PolymorphicBaseModelAdmin(admin.ModelAdmin):
    """
    A admin interface that can displays different change/delete pages,
    depending on the polymorphic model.
    """
    base_model = None
    add_type_template = None
    add_type_form = PolymorphicModelChoiceAdminForm


    @abc.abstractmethod
    def get_admin_for_model(self, model):
        raise NotImplementedError("Implement get_admin_for_model()")


    @abc.abstractmethod
    def get_polymorphic_model_classes(self):
        raise NotImplementedError("Implement get_polymorphic_model_classes()")


    def get_polymorphic_type_choices(self):
        """
        Return a list of polymorphic types which can be added.
        """
        from fluent_pages.extensions import page_type_pool

        choices = []
        for model in self.get_polymorphic_model_classes():
            ct = ContentType.objects.get_for_model(model)
            choices.append((ct.id, model._meta.verbose_name))
        return choices


    def _get_real_admin(self, object_id):
        obj = self.model.objects.non_polymorphic().values('polymorphic_ctype').get(pk=object_id)
        return self._get_real_admin_by_ct(obj['polymorphic_ctype'])


    def _get_real_admin_by_ct(self, ct_id):
        try:
            ct = ContentType.objects.get_for_id(ct_id)
        except ContentType.DoesNotExist as e:
            raise Http404(e)   # Handle invalid GET parameters

        model_class = ct.model_class()
        if not model_class:
            raise Http404("No model found for '{0}.{1}'.".format(*ct.natural_key()))  # Handle model deletion

        # The views are already checked for permissions, so ensure the model is a derived object.
        # Otherwise, it would open all admin views to users who can edit the base object.
        if not issubclass(model_class, self.base_model):
            raise PermissionDenied("Invalid model '{0}.{1}', must derive from {name}.".format(*ct.natural_key(), name=self.base_model.__name__))

        return self.get_admin_for_model(model_class)


    def queryset(self, request):
        return super(PolymorphicBaseModelAdmin, self).queryset(request).non_polymorphic()


    def add_view(self, request, form_url='', extra_context=None):
        """Redirect the add view to the real admin."""
        ct_id = int(request.GET.get('ct_id', 0))
        if not ct_id:
            # Display choices
            return self.add_type_view(request)
        else:
            real_admin = self._get_real_admin_by_ct(ct_id)
            return real_admin.add_view(request, form_url, extra_context)


    def change_view(self, request, object_id, extra_context=None):
        """Redirect the change view to the real admin."""
        real_admin = self._get_real_admin(object_id)
        return real_admin.change_view(request, object_id, extra_context)


    def delete_view(self, request, object_id, extra_context=None):
        """Redirect the delete view to the real admin."""
        real_admin = self._get_real_admin(object_id)
        return real_admin.delete_view(request, object_id, extra_context)


    def get_urls(self):
        """Support forwarding URLs."""
        urls = super(PolymorphicBaseModelAdmin, self).get_urls()
        info = self.model._meta.app_label, self.model._meta.module_name

        # Patch the change URL is not a big catch-all, so all custom URLs can be added to the end.
        # can't patch url.regex property directly, as it changed with Django 1.4's LocaleRegexProvider
        new_change_url = url(r'^(\d+)/$', self.admin_site.admin_view(self.change_view), name='{0}_{1}_change'.format(*info))
        for i, oldurl in enumerate(urls):
            if oldurl.name == new_change_url.name:
                urls[i] = new_change_url

        # Define the catch-all for custom views
        custom_urls = patterns('',
            url(r'^(?P<path>.+)$', self.admin_site.admin_view(self.subclass_view))
        )

        # Add reverse names for all polymorphic models, so the delete button and "save and add" works.
        from fluent_pages.extensions import page_type_pool
        dummy_urls = []
        for model in page_type_pool.get_model_classes():
            info = (model._meta.app_label, model._meta.module_name)
            dummy_urls += (
                url(r'^(\d+)/$', _dummy_change_view, name='{0}_{1}_change'.format(*info)),
                url(r'^add/$', _dummy_change_view, name='{0}_{1}_add'.format(*info)),
            )

        return urls + custom_urls + dummy_urls


    def subclass_view(self, request, path):
        """
        Forward any request to a custom view of the real admin.
        """
        ct_id = int(request.GET.get('ct_id', 0))
        if not ct_id:
            raise Http404("No ct_id parameter, unable to find admin subclass for path '{0}'.".format(path))

        real_admin = self._get_real_admin_by_ct(ct_id)
        resolver = RegexURLResolver('^', real_admin.urls)
        resolvermatch = resolver.resolve(path)
        if not resolvermatch:
            raise Http404("No match for path '{0}' in admin subclass.".format(path))

        return resolvermatch.func(request, *resolvermatch.args, **resolvermatch.kwargs)


    def add_type_view(self, request, form_url=''):
        """
        Display a choice form to select which page type to add.
        """
        extra_qs = ''
        if request.META['QUERY_STRING']:
            extra_qs = '&' + request.META['QUERY_STRING']

        choices = self.get_polymorphic_type_choices()
        if len(choices) == 1:
            return HttpResponseRedirect('?ct_id={0}{1}'.format(choices[0][0], extra_qs))

        # Create form
        form = self.add_type_form(
            data=request.POST if request.method == 'POST' else None,
            initial={'ct_id': choices[0][0]}
        )
        form.fields['ct_id'].choices = choices

        if form.is_valid():
            return HttpResponseRedirect('?ct_id={0}{1}'.format(form.cleaned_data['ct_id'], extra_qs))

        # Wrap in all admin layout
        fieldsets = ((None, {'fields': ('ct_id',)}),)
        adminForm = AdminForm(form, fieldsets, {}, model_admin=self)
        media = self.media + adminForm.media
        opts = self.model._meta

        context = {
            'title': _('Add %s') % force_unicode(opts.verbose_name),
            'adminform': adminForm,
            'is_popup': "_popup" in request.REQUEST,
            'media': mark_safe(media),
            'errors': AdminErrorList(form, ()),
            'app_label': opts.app_label,
        }
        return self.render_add_type_form(request, context)


    def render_add_type_form(self, request, context, form_url=''):
        """
        Render the page type choice form.
        """
        opts = self.model._meta
        app_label = opts.app_label
        context.update({
            'has_change_permission': self.has_change_permission(request),
            'form_url': mark_safe(form_url),
            'opts': opts,
        })
        if hasattr(self.admin_site, 'root_path'):
            context['root_path'] = self.admin_site.root_path  # Django < 1.4
        context_instance = RequestContext(request, current_app=self.admin_site.name)
        return render_to_response(self.add_type_template or [
            "admin/%s/%s/add_type_form.html" % (app_label, opts.object_name.lower()),
            "admin/%s/add_type_form.html" % app_label,
            "admin/add_type_form.html"
        ], context, context_instance=context_instance)



class PolymorphedModelAdmin(admin.ModelAdmin):
    """
    The optional base class for the admin interface of derived models,
    """
    base_model = None
    base_form = None
    base_fieldsets = None
    extra_fieldset_title = _("Contents")


    def get_form(self, request, obj=None, **kwargs):
        # The django admin validation requires the form to have a 'class Meta: model = ..'
        # attribute, or it will complain that the fields are missing.
        # However, this enforces all derived ModelAdmin classes to redefine the model as well,
        # because they need to explicitly set the model again - it will stick with the base model.
        #
        # Instead, pass the form unchecked here, because the standard ModelForm will just work.
        # If the derived class sets the model explicitly, respect that setting.
        if not self.form:
            kwargs['form'] = self.base_form
        return super(PolymorphedModelAdmin, self).get_form(request, obj, **kwargs)


    @property
    def change_form_template(self):
        opts = self.model._meta
        app_label = opts.app_label

        base_opts = self.base_model._meta
        base_app_label = base_opts.app_label

        return [
            "admin/%s/%s/change_form.html" % (app_label, opts.object_name.lower()),
            "admin/%s/change_form.html" % app_label,
            # Added:
            "admin/%s/%s/change_form.html" % (base_app_label, base_opts.object_name.lower()),
            "admin/%s/change_form.html" % base_app_label,
            "admin/change_form.html"
        ]


    @property
    def delete_confirmation_template(self):
        opts = self.model._meta
        app_label = opts.app_label

        base_opts = self.base_model._meta
        base_app_label = base_opts.app_label

        return [
            "admin/%s/%s/delete_confirmation.html" % (app_label, opts.object_name.lower()),
            "admin/%s/delete_confirmation.html" % app_label,
            # Added:
            "admin/%s/%s/delete_confirmation.html" % (base_app_label, base_opts.object_name.lower()),
            "admin/%s/delete_confirmation.html" % base_app_label,
            "admin/delete_confirmation.html"
        ]


    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context.update({
            'base_opts': self.base_model._meta,
        })
        return super(PolymorphedModelAdmin, self).render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)


    def delete_view(self, request, object_id, context=None):
        extra_context = {
            'base_opts': self.base_model._meta,
        }
        return super(PolymorphedModelAdmin, self).delete_view(request, object_id, extra_context)


    # ---- Extra: improving the form/fieldset default display ----

    def get_fieldsets(self, request, obj=None):
        # If subclass declares fieldsets, this is respected
        if self.declared_fieldsets:
            return super(PolymorphedModelAdmin, self).get_fieldsets(request, obj)

        # Have a reasonable default fieldsets,
        # where the subclass fields are automatically included.
        other_fields = self.get_subclass_fields(request, obj)

        if other_fields:
            return (
                self.base_fieldsets[0],
                (self.extra_fieldset_title, {'fields': other_fields}),
            ) + self.base_fieldsets[1:]
        else:
            return self.base_fieldsets


    def get_subclass_fields(self, request, obj=None):
        # Find out how many fields would really be on the form,
        # if it weren't restricted by declared fields.
        exclude = list(self.exclude or [])
        exclude.extend(self.get_readonly_fields(request, obj))

        # By not declaring the fields/form in the base class,
        # get_form() will populate the form with all available fields.
        form = self.get_form(request, obj, exclude=exclude)
        subclass_fields = form.base_fields.keys() + list(self.get_readonly_fields(request, obj))

        # Find which fields are not part of the common fields.
        for fieldset in self.base_fieldsets:
            for field in fieldset[1]['fields']:
                subclass_fields.remove(field)
        return subclass_fields