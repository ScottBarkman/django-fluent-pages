from django.conf import settings
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from mptt.forms import MPTTAdminForm
from polymorphic_tree.admin import PolymorphicMPTTChildModelAdmin
from fluent_pages import appsettings
from parler.admin import TranslatableAdmin
from parler.forms import TranslatableModelForm, TranslatedField
from fluent_pages.models import UrlNode, UrlNode_Translation
from fluent_pages.forms.fields import RelativeRootPathField
import mptt


class UrlNodeAdminForm(MPTTAdminForm, TranslatableModelForm):
    """
    The admin form for the main fields (the ``UrlNode`` object).
    """
    # Using a separate formfield to display the full URL in the override_url field:
    # - The override_url is stored relative to the URLConf root,
    #   which makes the site easily portable to another path or root.
    # - Users don't have to know or care about this detail.
    #   They only see the absolute external URLs, so make the input reflect that as well.
    title = TranslatedField()
    slug = TranslatedField()
    override_url = TranslatedField(form_class=RelativeRootPathField)

    def __init__(self, *args, **kwargs):
        if 'parent' not in self.base_fields and mptt.VERSION[:2] == (0, 6):
            # Skip bug in django-mptt 0.6.0
            # https://github.com/django-mptt/django-mptt/issues/275
            TranslatableModelForm.__init__(self, *args, **kwargs)
        else:
            super(UrlNodeAdminForm, self).__init__(*args, **kwargs)

    def clean(self):
        """
        Extend valiation of the form, checking whether the URL is unique.
        Returns all fields which are valid.
        """
        # As of Django 1.3, only valid fields are passed in cleaned_data.
        cleaned_data = super(UrlNodeAdminForm, self).clean()

        # See if the current URLs don't overlap.
        all_translations = UrlNode_Translation.objects.all()
        if appsettings.FLUENT_PAGES_FILTER_SITE_ID:
            site_id = (self.instance is not None and self.instance.parent_site_id) or settings.SITE_ID
            all_translations = all_translations.filter(master__parent_site=site_id)

        if self.instance and self.instance.id:
            # Editing an existing page
            current_id = self.instance.id
            other_translations = all_translations.exclude(master_id=current_id)

            # Get original unmodified parent value.
            try:
                parent = UrlNode.objects.non_polymorphic().get(children__pk=current_id)
            except UrlNode.DoesNotExist:
                parent = None
        else:
            # Creating new page!
            parent = cleaned_data['parent']
            other_translations = all_translations

        # If fields are filled in, and still valid, check for unique URL.
        # Determine new URL (note: also done in UrlNode model..)
        if cleaned_data.get('override_url'):
            new_url = cleaned_data['override_url']

            if other_translations.filter(_cached_url=new_url).count():
                self._errors['override_url'] = self.error_class([_('This URL is already taken by an other page.')])
                del cleaned_data['override_url']

        elif cleaned_data.get('slug'):
            new_slug = cleaned_data['slug']
            if parent:
                new_url = '%s%s/' % (parent._cached_url, new_slug)
            else:
                new_url = '/%s/' % new_slug

            if other_translations.filter(_cached_url=new_url).count():
                self._errors['slug'] = self.error_class([_('This slug is already used by an other page at the same level.')])
                del cleaned_data['slug']

        return cleaned_data



class UrlNodeChildAdmin(PolymorphicMPTTChildModelAdmin, TranslatableAdmin):
    """
    The internal machinery
    The admin screen for the ``UrlNode`` objects.
    """
    base_model = UrlNode
    base_form = UrlNodeAdminForm


    # Expose fieldsets for subclasses to reuse
    #: The general fieldset to display
    FIELDSET_GENERAL = (None, {
        'fields': ('title', 'slug', 'status', 'in_navigation'),
    })
    #: The menu fieldset
    FIELDSET_MENU = (_('Menu structure'), {
        'fields': ('parent',),
        'classes': ('collapse',),
    })
    #: The publication fields.
    FIELDSET_PUBLICATION = (_('Publication settings'), {
        'fields': ('publication_date', 'publication_end_date', 'override_url'),
        'classes': ('collapse',),
    })

    #: The fieldsets to display.
    #: Any missing fields will be displayed in a separate section (named :attr:`extra_fieldset_title`) automatically.
    base_fieldsets = (
        FIELDSET_GENERAL,
        FIELDSET_MENU,
        FIELDSET_PUBLICATION,
    )

    # Config add/edit page:
    raw_id_fields = ('parent',)
    radio_fields = {'status': admin.HORIZONTAL}
    readonly_shared_fields = ('status', 'in_navigation', 'parent', 'publication_date', 'publication_end_date',)

    # The static prepopulated_fields attribute is validated and fails.
    # The object function does work, and django-parler provides the media
    def get_prepopulated_fields(self, request, obj=None):
        return {
            'slug': ('title',)
        }

    # NOTE: list page is configured in UrlNodeParentAdmin
    # as that class is used for the real admin screen.
    # This class is only a base class for the custom pagetype plugins.


    def queryset(self, request):
        qs = super(UrlNodeChildAdmin, self).queryset(request)

        # Admin only shows current site for now,
        # until there is decent filtering for it.
        if appsettings.FLUENT_PAGES_FILTER_SITE_ID:
            qs = qs.filter(parent_site=settings.SITE_ID)
        return qs


    def get_readonly_fields(self, request, obj=None):
        fields = super(UrlNodeChildAdmin, self).get_readonly_fields(request, obj)
        if obj is not None:
            # Edit screen
            if obj.get_available_languages().count() >= 2 \
            and not self.has_change_shared_fields_permission(request, obj):
                # This page is translated in multiple languages,
                # language team is only allowed to update their own language.
                fields += self.readonly_shared_fields
        return fields


    def has_change_shared_fields_permission(self, request, obj=None):
        """
        Whether the user can change the page layout.
        """
        codename = '{0}.change_shared_fields_urlnode'.format(obj._meta.app_label)
        return request.user.has_perm(codename, obj=obj)


    def formfield_for_dbfield(self, db_field, **kwargs):
        """
        Allow formfield_overrides to contain field names too.
        """
        overrides = self.formfield_overrides.get(db_field.name)
        if overrides:
            kwargs.update(overrides)

        return super(UrlNodeChildAdmin, self).formfield_for_dbfield(db_field, **kwargs)


    def save_model(self, request, obj, form, change):
        # Automatically store the user in the author field.
        if not change:
            obj.author = request.user

        super(UrlNodeChildAdmin, self).save_model(request, obj, form, change)
