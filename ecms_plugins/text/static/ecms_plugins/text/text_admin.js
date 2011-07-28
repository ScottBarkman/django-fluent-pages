(function($){

  var has_load_error = false;
  var is_first_init = true;


  // A bit of a HACK, maybe needs migration later on:
  function init_wysiwyg()
  {
    if( ! is_first_init ) return;
    is_first_init = false;

    // Extra customizations for the YUI editor
    if( window.django_wysiwyg_editor_config && window.YAHOO )
    {
      window.django_wysiwyg_editor_config.height = "150px";
      window.django_wysiwyg_editor_config.autoHeight = true;
    }
  }


  function disable_wysiwyg(root)
  {
    var textareas = root.find("textarea.vLargeTextField:not([id=~__prefix__])").toArray();
    for(var i = 0; i < textareas.length; i++)
    {
      var textarea = textareas[i];
      django_wysiwyg.disable("e:" + textarea.name);
    }
  }


  function enable_wysiwyg(root)
  {
    init_wysiwyg();
    var textareas = root.find("textarea.vLargeTextField:not([id=~__prefix__])").debug();

    if( ! django_wysiwyg.is_loaded() )
    {
      textareas.show();

      // Show an error message, but just once.
      if( ! has_load_error )
      {
        textareas.before("<p><em style='color:#cc3333'>Unable to load WYSIWYG editor, is the system connected to the Internet?</em></p>");
        has_load_error = true;
      }

      return;
    }

    textareas = textareas.toArray();
    for(var i = 0; i < textareas.length; i++)
    {
      var textarea = textareas[i];
      django_wysiwyg.enable("e:" + textarea.name, textarea.id);
    }
  }


  // Make sure the WYSIWYG editor is loaded for our models.
  ecms_plugins.register_view_handler('CmsTextItem', {
    'enable': enable_wysiwyg,
    'disable': disable_wysiwyg
  })

})(window.jQuery || django.jQuery);
