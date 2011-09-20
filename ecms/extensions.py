"""
Special classes to extend the CMS; e.g. plugins.

The extension mechanism is provided for projects that benefit
from a tighter integration then the Django URLconf can provide.
"""
from django.conf import settings
from django import forms
from django.core import context_processors
from django.template.context import Context
from django.template.loader import render_to_string
from django.utils.html import linebreaks, escape
from django.utils.importlib import import_module
from django.utils.translation import ugettext as _
from ecms.models import CmsPageItem

# The API uses a registration system.
# While plugins can be easily detected via ``__subclasses__()``, this is more magic and less explicit.
# Having to do an explicit register ensures future compatibility with other API's like reversion.
#
# This mechanism is mostly inspired by Django CMS,
# which nice job at defining a clear extension model.
# (c) Django CMS developers, BSD licensed.

PLUGIN_CATEGORIES = {
    None: '',
    'text': _('Text'),
    'media': _('Media'),
    'programming': _('Programming'),
    'advanced': _('Advanced'),
    'unknown': _('Unknown'),
}

# Some standard request processors to use in the plugins,
# Naturally, you want STATIC_URL to be available in plugins.
_STANDARD_REQUEST_CONTEXT_PROCESSORS = (
    context_processors.request,
    context_processors.static,
    context_processors.media,
    context_processors.i18n,
)

class EcmsPluginContext(Context):
    """
    A template Context class similar to RequestContext, that enters some prefilled data.
    """
    def __init__(self, request, dict=None, current_app=None):
        # If there is any reason to site-global context processors for plugins,
        # I'd like to know the usecase, and it could be implemented here.
        Context.__init__(self, dict, current_app=current_app)
        for processor in _STANDARD_REQUEST_CONTEXT_PROCESSORS:
            self.update(processor(request))


class CmsPageItemForm(forms.ModelForm):
    """
    The base form for custom pageitem types.
    """
    region = forms.CharField(widget=forms.HiddenInput(), required=False)
    sort_order = forms.IntegerField(widget=forms.HiddenInput(), initial=1)


class EcmsPlugin(object):
    """
    The base class for a plugin, defining the settings.
    """
    __metaclass__ = forms.MediaDefiningClass

    # Settings to override
    model = None  # CmsPageItem derived
    admin_form = CmsPageItemForm
    admin_form_template = "admin/ecms/cmspageitem/admin_form.html"
    render_template = None
    category = None


    @property
    def verbose_name(self):
        """
        Return the title for the plugin.
        """
        return self.model._meta.verbose_name


    @property
    def type_name(self):
        """
        Return the classname of the model.
        """
        return self.model.__name__


    @classmethod
    def get_model_instances(cls, page):
        """
        Return the model instances the plugin has added at the page.
        """
        return cls.model.objects.filter(parent=page)


    @classmethod
    def _render_pageitem(cls, instance, request):
        # Internal wrapper for render(), to allow updating the method signature easily.
        # It also happens to really simplify code navigation.
        return cls.render(instance=instance, request=request)


    @classmethod
    def render(cls, instance, request, **kwargs):
        """
        The rendering/view function that displays a plugin model instance.
        It is recommended to wrap the output in a <div> object, so the item is not inlined after the previous plugin.

        To render a plugin, either override this function, or specify the ``render_template`` variable,
        and optionally override ``get_context()``.
        """
        if cls.render_template:
            context = cls.get_context(instance, request)
            return render_to_string(cls.render_template, context, context_instance=EcmsPluginContext(request))
        else:
            return unicode(_(u"{No rendering defined for class '%s'}" % cls.__name__))


    @classmethod
    def get_context(cls, instance, request, **kwargs):
        return {
            'instance': instance,
            'ecms_page': instance.parent,
        }



# -------- Some utils --------

def _import_apps_submodule(submodule):
    """
    Look for a submodule is a series of packages, e.g. ".ecms_plugins" in all INSTALLED_APPS.
    """
    for app in settings.INSTALLED_APPS:
        try:
            import_module('.' + submodule, app)
        except ImportError, e:
            if submodule not in str(e):
                raise   # import error is a level deeper.
            else:
                pass


def render_error(error):
    return '<div style="color: red; border: 1px solid red; padding: 5px;">' \
              '<p><strong>%s</strong></p>%s</div>' % (_('Error:'), linebreaks(escape(str(error))))


# -------- API to access plugins --------

class PluginAlreadyRegistered(Exception):
    pass


class PluginPool(object):
    """
    The central administration of plugins.
    """

    def __init__(self):
        self.plugins = {}
        self.detected = False

    def register(self, plugin):
        """
        Make a plugin known by the CMS.

        If a plugin is already registered, this will raise PluginAlreadyRegistered.
        """
        assert issubclass(plugin, EcmsPlugin) and plugin.__name__ != 'EcmsPlugin', "The plugin must inherit from `EcmsPlugin`"
        assert plugin.model, "The plugin has no model defined"
        assert issubclass(plugin.model, CmsPageItem) and plugin.model.__name__ != 'CmsPageItem', "The plugin model must inherit from `CmsPageItem`"

        name = plugin.__name__
        if name in self.plugins:
            raise PluginAlreadyRegistered("[%s] a plugin with this name is already registered" % name)

        plugin.model._ecms_plugin = plugin   # makes things a lot easier down the road (at rendering).
        self.plugins[name] = plugin


    def get_plugin_classes(self):
        """
        Return the list of all plugin classes which are loaded.
        """
        self._import_plugins()
        return self.plugins.values()


    def get_page_item_classes(self):
        """
        Return all page item models which are exposed by plugins.
        """
        self._import_plugins()
        return [plugin.model for plugin in self.plugins.values()]


    def _import_plugins(self):
        """
        Internal function, ensure all plugin packages are imported.
        """
        if self.detected:
            return
        _import_apps_submodule("ecms_plugins")
        self.detected = True

plugin_pool = PluginPool()
