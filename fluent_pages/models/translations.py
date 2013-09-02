"""
Simple but effective translation support.

Integrating *django-hvad* (v0.3) turned out to be really hard,
as it changes the behavior of the QuerySet iterator, manager methods
and model metaclass which *django-polymorphic* also rely on.
The following is a "crude, but effective" way to introduce multilingual support.
"""
from django.db import models
from django.utils.translation import get_language
from fluent_pages import appsettings
from fluent_pages.utils.i18n import normalize_language_code


class TranslatableModel(models.Model):
    """
    Base model class to handle translations.
    """

    # Consider these fields "protected" or "internal" attributes.
    # Not part of the public API, but used internally in the class hierarchy.
    _translations_field = 'translations'
    _translations_model = None
    _translations_model_doesnotexist = None

    class Meta:
        abstract = True


    def __init__(self, *args, **kwargs):
        # Still allow to pass the translated fields (e.g. title=...) to this function.
        translated_kwargs = {}
        current_language = None
        if kwargs:
            current_language = kwargs.get('_current_language', None)
            for field in self._translations_model.get_translated_fields():
                try:
                    translated_kwargs[field] = kwargs.pop(field)
                except KeyError:
                    pass

        # Run original Django model __init__
        super(TranslatableModel, self).__init__(*args, **kwargs)

        self._translations_cache = {}
        self._current_language = normalize_language_code(current_language or get_language())  # What you used to fetch the object is what you get.

        # Assign translated args manually.
        if translated_kwargs:
            translation = self._get_translated_model(auto_create=True)
            for field, value in translated_kwargs.iteritems():
                setattr(translation, field, value)

            # Check if other translations were also modified
            for code, obj in self._translations_cache.iteritems():
                if code != translation.language_code and obj.is_modified:
                    obj.save()


    def get_current_language(self):
        # not a property, so won't conflict with model fields.
        return self._current_language


    def set_current_language(self, language_code, initialize=False):
        self._current_language = normalize_language_code(language_code or get_language())

        # Ensure the translation is present for __get__ queries.
        if initialize:
            self._get_translated_model(use_fallback=False, auto_create=True)


    def get_available_languages(self):
        """
        Return the language codes of all translated variations.
        """
        return self._translations_model.objects.filter(master=self).values_list('language_code', flat=True)


    def _get_translated_model(self, language_code=None, use_fallback=False, auto_create=False):
        """
        Fetch the translated fields model.
        """
        if not language_code:
            language_code = self._current_language

        # 1. fetch the object from the cache
        object = None
        try:
            object = self._translations_cache[language_code]

            # If cached object indicates the language doesn't exist, need to query the fallback.
            if object is not None:
                return object
        except KeyError:
            # 2. No cache, need to query
            # Get via self.TRANSLATIONS_FIELD.get(..) so it also uses the prefetch/select_related cache.
            accessor = getattr(self, self._translations_field)
            try:
                object = accessor.get(language_code=language_code)
            except self._translations_model.DoesNotExist:
                pass

        if object is None:
            # Not in cache, or default.
            # Not fetched from DB

            # 3. Alternative solutions
            if auto_create:
                # Auto create policy first (e.g. a __set__ call)
                object = self._translations_model(
                    language_code=language_code,
                    master=self  # ID might be None at this point
                )
            elif use_fallback and (appsettings.FLUENT_PAGES_DEFAULT_LANGUAGE_CODE != language_code):
                # Jump to fallback language, return directly.
                # Don't cache under this language_code
                self._translations_cache[language_code] = None   # explicit marker that language query was tried before.
                return self._get_translated_model(appsettings.FLUENT_PAGES_DEFAULT_LANGUAGE_CODE, use_fallback=False, auto_create=auto_create)
            else:
                # None of the above, bail out!
                exception_class = (self._translations_model_doesnotexist or self._translations_model.DoesNotExist)
                raise exception_class(
                    u"{0} does not have a translation for the current language!\n"
                    u"{0} ID #{1}, language={2}".format(self._meta.verbose_name, self.pk, language_code
                ))

        # Cache and return
        self._translations_cache[language_code] = object
        return object


    def save(self, *args, **kwargs):
        super(TranslatableModel, self).save(*args, **kwargs)
        self.save_translations()


    def save_translations(self):
        # Also save translated strings.
        translations = self._get_translated_model()
        if translations.is_modified:
            if not translations.master_id:  # Might not exist during first construction
                translations.master = self
            translations.save()



class TranslatedFieldsModel(models.Model):
    """
    Base class for the model that holds the translated fields.
    """
    language_code = models.CharField(max_length=15, db_index=True)
    master = None   # FK to shared model.

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(TranslatedFieldsModel, self).__init__(*args, **kwargs)
        self._original_values = self._get_field_values()

    @property
    def is_modified(self):
        return self._original_values != self._get_field_values()

    def save(self, *args, **kwargs):
        super(TranslatedFieldsModel, self).save(*args, **kwargs)
        self._original_values = self._get_field_values()

    def _get_field_values(self):
        # Return all field values in a consistent (sorted) manner.
        return [getattr(self, field) for field in self._meta.get_all_field_names()]

    @classmethod
    def get_translated_fields(self):
        fields = self._meta.get_all_field_names()
        fields.remove('language_code')
        fields.remove('master')
        fields.remove('id')   # exists with deferred objects that .only() queries create.
        return fields

    def __unicode__(self):
        return unicode(self.pk)

    def __repr__(self):
        return "<{0}: #{1}, {2}, master: #{3}>".format(
            self.__class__.__name__, self.pk, self.language_code, self.master_id
        )



class TranslatedAttribute(object):
    """
    Descriptor for translated attributes.
    Currently placed manually on the class (no metaclass magic involved here).
    """
    def __init__(self, name):
        self.name = name

    def __get__(self, instance, instance_type=None):
        if not instance:
            # Return the class attribute when asked for by the admin.
            return instance_type._translations_model._meta.get_field_by_name(self.name)[0]

        # Auto create is useless for __get__, will return empty titles everywhere.
        # Better use a fallback instead, just like gettext does.
        translation = instance._get_translated_model(use_fallback=True)
        return getattr(translation, self.name)

    def __set__(self, instance, value):
        # When assigning the property, assign to the current language.
        # No fallback is used in this case.
        translation = instance._get_translated_model(use_fallback=False, auto_create=True)
        setattr(translation, self.name, value)

    def __delete__(self, instance):
        # No autocreate or fallback, as this is delete.
        # Rather blow it all up when the attribute doesn't exist.
        # Similar to getting a KeyError on `del dict['UNKNOWN_KEY']`
        translation = instance._get_translated_model()
        delattr(translation, self.name)
