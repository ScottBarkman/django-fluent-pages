"""
Translation support for admin forms.
"""
from django.conf import settings
from django.conf.urls import patterns, url
from django.contrib import admin
from django.contrib.admin.options import csrf_protect_m
from django.contrib.admin.util import get_deleted_objects, unquote
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import router
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render
from django.utils.encoding import iri_to_uri, force_unicode
from django.utils.translation import get_language, ugettext_lazy as _
from fluent_pages import appsettings
from fluent_pages.utils.compat import transaction_atomic
from fluent_pages.utils.i18n import normalize_language_code


def get_model_form_field(model, name, **kwargs):
    return model._meta.get_field_by_name(name)[0].formfield(**kwargs)


def get_language_title(language_code):
    try:
        return next(title for code, title in settings.LANGUAGES if code == language_code)
    except StopIteration:
        return language_code


class TranslatableModelFormMixin(object):
    """
    Form mixin, to fetch+store translated fields.
    """
    _translatable_model = None
    _translatable_fields = ()
    language_code = None   # Set by get_form()


    def __init__(self, *args, **kwargs):
        super(TranslatableModelFormMixin, self).__init__(*args, **kwargs)

        # Load the initial values for the translated fields
        instance = kwargs.get('instance', None)
        if instance:
            translation = instance._get_translated_model(auto_create=True)
            for field in self._translatable_fields:
                self.initial.setdefault(field, getattr(translation, field))


    def save(self, commit=True):
        self.instance.set_current_language(self.language_code)
        # Assign translated fields to the model (using the TranslatedAttribute descriptor)
        for field in self._translatable_fields:
            setattr(self.instance, field, self.cleaned_data[field])

        return super(TranslatableModelFormMixin, self).save(commit)



class TranslatableAdmin(admin.ModelAdmin):
    """
    Base class for translated admins
    """
    # Code partially taken from django-hvad

    class Media:
        css = {
            'all': ('fluent_pages/admin/language_tabs.css',)
        }

    deletion_not_allowed_template = 'admin/fluent_pages/page/deletion_not_allowed.html'

    query_language_key = 'language'


    def _language(self, request, obj=None):
        if not appsettings.is_multilingual():
            # By default, the pages are stored in a single static language.
            # This makes the transition to multilingual easier as well.
            # The default language can operate as fallback language too.
            return appsettings.FLUENT_PAGES_DEFAULT_LANGUAGE_CODE
        else:
            # In multilingual mode, take the provided language of the request.
            code = request.GET.get(self.query_language_key)

            if not code:
                # Show first tab by default
                try:
                    lang_choices = appsettings.FLUENT_PAGES_LANGUAGES[settings.SITE_ID]
                    code = lang_choices[0]['code']
                except (KeyError, IndexError):
                    # No configuration, always fallback to default language.
                    # This is essentially a non-multilingual configuration.
                    code = appsettings.FLUENT_PAGES_DEFAULT_LANGUAGE_CODE

            return normalize_language_code(code)

    def get_object(self, request, object_id):
        """
        Make sure the object is fetched in the correct language.
        """
        obj = super(TranslatableAdmin, self).get_object(request, object_id)
        if obj is not None:
            obj.set_current_language(self._language(request, obj), initialize=True)

        return obj

    def get_form(self, request, obj=None, **kwargs):
        form_class = super(TranslatableAdmin, self).get_form(request, obj, **kwargs)
        form_class.language_code = obj.get_current_language() if obj is not None else self._language(request)
        return form_class

    def get_urls(self):
        urlpatterns = super(TranslatableAdmin, self).get_urls()
        info = self.model._meta.app_label, self.model._meta.module_name

        return patterns('',
            url(r'^(.+)/delete-translation/(.+)/$',
                self.admin_site.admin_view(self.delete_translation),
                name='{0}_{1}_delete_translation'.format(*info)
            ),
        ) + urlpatterns

    def get_available_languages(self, obj):
        if obj:
            return obj.get_available_languages()
        else:
            return self.model._translations_model.objects.get_empty_query_set()

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        lang_code = obj.get_current_language() if obj is not None else self._language(request)
        lang = get_language_title(lang_code)
        available_languages = self.get_available_languages(obj)
        context['current_is_translated'] = lang_code in available_languages
        context['allow_deletion'] = len(available_languages) > 1
        context['language_tabs'] = self.get_language_tabs(request, obj, available_languages)
        if context['language_tabs']:
            context['title'] = '%s (%s)' % (context['title'], lang)
        #context['base_template'] = self.get_change_form_base_template()
        return super(TranslatableAdmin, self).render_change_form(request, context, add, change, form_url, obj)

    def response_add(self, request, obj, post_url_continue=None):
        redirect = super(TranslatableAdmin, self).response_add(request, obj, post_url_continue)
        return self._patch_redirect(request, obj, redirect)

    def response_change(self, request, obj):
        redirect = super(TranslatableAdmin, self).response_change(request, obj)
        return self._patch_redirect(request, obj, redirect)

    def _patch_redirect(self, request, obj, redirect):
        if redirect.status_code not in (301,302):
            return redirect  # a 200 response likely.

        uri = iri_to_uri(request.path)
        info = (self.model._meta.app_label, self.model._meta.module_name)

        # Pass ?language=.. to next page.
        continue_urls = (uri, "../add/", reverse('admin:{0}_{1}_add'.format(*info)))
        if redirect['Location'] in continue_urls and self.query_language_key in request.GET:
            # "Save and add another" / "Save and continue" URLs
            redirect['Location'] += "?{0}={1}".format(self.query_language_key, request.GET[self.query_language_key])
        return redirect

    def get_language_tabs(self, request, obj, available_languages):
        tabs = []
        get = request.GET.copy()  # QueryDict object
        language = obj.get_current_language() if obj is not None else self._language(request)
        tab_languages = []

        base_url = '{0}://{1}{2}'.format(request.is_secure() and 'https' or 'http', request.get_host(), request.path)

        for lang_dict in appsettings.FLUENT_PAGES_LANGUAGES.get(settings.SITE_ID, ()):
            code = lang_dict['code']
            title = get_language_title(code)
            get['language'] = code
            url = '{0}?{1}'.format(base_url, get.urlencode())

            if code == language:
                status = 'current'
            elif code in available_languages:
                status = 'available'
            else:
                status = 'empty'

            tabs.append((url, title, code, status))
            tab_languages.append(code)

        # Additional stale translations in the database?
        if appsettings.FLUENT_PAGES_SHOW_EXCLUDED_LANGUAGE_TABS:
            for code in available_languages:
                if code not in tab_languages:
                    get['language'] = code
                    url = '{0}?{1}'.format(base_url, get.urlencode())

                    if code == language:
                        status = 'current'
                    else:
                        status = 'available'

                    tabs.append((url, get_language_title(code), code, status))

        return tabs

    @csrf_protect_m
    @transaction_atomic
    def delete_translation(self, request, object_id, language_code):
        """
        The 'delete translation' admin view for this model.
        """
        opts = self.model._meta
        translations_model = self.model._translations_model

        try:
            translation = translations_model.objects.select_related('master').get(master=unquote(object_id), language_code=language_code)
        except translations_model.DoesNotExist:
            raise Http404

        if not self.has_delete_permission(request, translation):
            raise PermissionDenied

        if self.get_available_languages(translation.master).count() <= 1:
            return self.deletion_not_allowed(request, translation, language_code)

        # Populate deleted_objects, a data structure of all related objects that
        # will also be deleted.

        using = router.db_for_write(translations_model)
        lang = get_language_title(language_code)
        (deleted_objects, perms_needed, protected) = get_deleted_objects(
            [translation], translations_model._meta, request.user, self.admin_site, using)

        if request.POST: # The user has already confirmed the deletion.
            if perms_needed:
                raise PermissionDenied
            obj_display = _('{0} translation of {1}').format(lang, force_unicode(translation))  # in hvad: (translation.master)

            self.log_deletion(request, translation, obj_display)
            self.delete_model_translation(request, translation)
            self.message_user(request, _('The %(name)s "%(obj)s" was deleted successfully.') % dict(
                name=force_unicode(opts.verbose_name), obj=force_unicode(obj_display)
            ))

            if self.has_change_permission(request, None):
                return HttpResponseRedirect(reverse('admin:{0}_{1}_changelist'.format(opts.app_label, opts.module_name)))
            else:
                return HttpResponseRedirect(reverse('admin:index'))

        object_name = _('{0} Translation').format(force_unicode(opts.verbose_name))
        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": object_name}
        else:
            title = _("Are you sure?")

        context = {
            "title": title,
            "object_name": object_name,
            "object": translation,
            "deleted_objects": deleted_objects,
            "perms_lacking": perms_needed,
            "protected": protected,
            "opts": opts,
            "app_label": opts.app_label,
        }

        return render(request, self.delete_confirmation_template or [
            "admin/%s/%s/delete_confirmation.html" % (opts.app_label, opts.object_name.lower()),
            "admin/%s/delete_confirmation.html" % opts.app_label,
            "admin/delete_confirmation.html"
        ], context)

    def deletion_not_allowed(self, request, obj, language_code):
        opts = self.model._meta
        context = {
            'object': obj.master,
            'language_code': language_code,
            'opts': opts,
            'app_label': opts.app_label,
            'language_name': get_language_title(language_code),
            'object_name': force_unicode(opts.verbose_name)
        }
        return render(request, self.deletion_not_allowed_template, context)

    def delete_model_translation(self, request, translation):
        translation.delete()
