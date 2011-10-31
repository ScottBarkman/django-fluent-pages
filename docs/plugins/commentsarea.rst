.. _ecms_plugins.commentsarea:

The ecms_plugins.commentsarea module
====================================

The `commentsarea`  plugin displays the form and messagelist
that `django.contrib.comments <https://docs.djangoproject.com/en/dev/ref/contrib/comments/>`_ renders.

By default, the displayed comments will look very plain. This is however, not an accident.
The `django.contrib.comments` module provides these defaults to make it fully customizable
to the design and workflow of the web site where it is being used.
Hence, this plugin depends on a properly configured `django.contrib.comments` module.

Installation
------------

Add the following settings to ``settings.py``:

.. code-block:: python

    INSTALLED_APPS += (
        'django.contrib.comments',
        'ecms_plugins.commentsarea',
    )

The `django.contrib.comments` module also requires a location for it's pages.
Add the following to ``urls.py``:

.. code-block:: python

    urlpatterns += patterns('',
        url(r'^blog/comments/', include('django.contrib.comments.urls')),
    )

This URL can be anything off course, like ``/comments/``, ``/respond/comments/`` or ``/blog/comments/`` for example.

Configuration
-------------

After the installation, each page can be enriched with a comments area.
Posting a comment however, produces an almost blank page.
That's because ``comments/base.html`` has to be overwritten.

To get a usable comments module, the least you need to do, is providing two templates:

* ``comments/base.html``
* ``comments/posted.html``

The base.html template
~~~~~~~~~~~~~~~~~~~~~~

The ``comments/base.html`` template is used by every template of the comments module.
It needs to provide two blocks;

* **title**: the sub title to display in the ``<title>`` tag.
* **content**: the content to display in the ``<body>`` tag.

These blocks can be mapped to your site template.
It's contents could be something like:

.. code-block:: html+django

    {% extends "mysite/base.html" %}{% load i18n %}

    {% block headtitle %}{% block title %}{% trans "Responses for page" %}{% endblock %}{% endblock %}

    {% block main %}
              <div id="content" class="clearfix">
                {% block content %}{% endblock %}
              </div>
    {% endblock %}

The :file:`comments/base.html` file can be stored in the :file:`templates` folder of your site theme.

The posted.html template
~~~~~~~~~~~~~~~~~~~~~~~~

The final "Thank you for posting" page is also quite plain.
Replace it be something more fresh by overriding the :file:`comments/posted.html` template.
For example, try something like:

.. code-block:: html+django

    {% extends "comments/base.html" %}{% load i18n %}

    {% block title %}{% trans "Thanks for commenting" %}{% endblock %}

    {% block extrahead %}
    {{ block.super }}
        <meta http-equiv="Refresh" content="5; url={{ comment.content_object.get_absolute_url }}#c{{ comment.id }}" />
    {% endblock %}

    {% block content %}
        <h1>Thank you for responding</h1>
        <p>
          We have received your comment, and added it to the web site.<br />
          You will be sent back to the article...
        </p>

        {# Using identical formatting to normal comment list #}
        <dl id="comments">
          <dt id="c{{ comment.id }}">
            {{ comment.submit_date }} - {{ comment.name }}
          </dt>
          <dd>
            <p>{{ comment.comment }}</p>
          </dd>
        </dl>

        <p><a href="{{ comment.content_object.get_absolute_url }}#c{{ comment.id }}">Back to the article</a></p>
    {% endblock %}

The template now contains links back to the blog page, and no longer appears as dead end.
It will automatically redirect back to the blog in a few seconds.

Additional configuration
~~~~~~~~~~~~~~~~~~~~~~~~

The `django.contrib.comments` module can be further extended with other modules.
In fact, `django.contrib.comments` only establishes a standard methology for integrating comments to a Django site.
The framework also supports moderation, flagging, and RSS feeds too. More documentation can be found at:

* `Django's comments framework <https://docs.djangoproject.com/en/dev/ref/contrib/comments/>`_
* `Customizing the comments framework <http://docs.djangoproject.com/en/dev/ref/contrib/comments/custom/>`_
* `Example of using the in-built comments app <http://docs.djangoproject.com/en/dev/ref/contrib/comments/example/>`_

Some of the modules worth looking at are:

* `django-ajaxcomments <https://bitbucket.org/bkonkle/django-ajaxcomments/>`_
* `django-comments-spamfighter <https://github.com/bartTC/django-comments-spamfighter>`_
* `django-threadedcomments <https://github.com/HonzaKral/django-threadedcomments>`_
* `django-myrecaptcha <https://bitbucket.org/pelletier/django-myrecaptcha/>`_

These modules can enhance the commentsarea even further.
