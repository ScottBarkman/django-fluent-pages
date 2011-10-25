.. _ecms_plugins.code:

The ecms_plugins.code module
============================

The `code` plugin provides highlighting for programming code.

The plugin uses `Pygments <http://pygments.org/>`_ as backend to perform the highlighting.

Installation
------------

Add the following settings to ``settings.py``:

.. code-block:: python

    INSTALLED_APPS += (
        'ecms_plugins.code',
    )

The dependencies can be installed via `pip`::

    pip install Pygments

Configuration
-------------

No settings have to be defined.
For further tuning however, the following settings are available:

.. code-block:: python

    ECMS_CODE_DEFAULT_LANGUAGE = 'python'
    ECMS_CODE_DEFAULT_LINE_NUMBERS = False

    ECMS_CODE_STYLE = 'default'

    ECMS_CODE_SHORTLIST = ('python', 'html', 'css', 'js')
    ECMS_CODE_SHORTLIST_ONLY = False


ECMS_CODE_DEFAULT_LANGUAGE
~~~~~~~~~~~~~~~~~~~~~~~~~~

Define which programming language should be selected by default.

This setting is ideally suited to set personal preferences.

ECMS_CODE_DEFAULT_LINE_NUMBERS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Define whether line number should be enabled by default for any new plugins.

ECMS_CODE_STYLE
~~~~~~~~~~~~~~~~~~~~~~~

The desired highlighting style. This can be any of the themes that Pygments provides.

Each style name refers to a python module in the :mod:`pygments.styles` package.
The styles provided by Pygments 1.4 are:

* *autumn*
* *borland*
* *bw* (black-white)
* *colorful*
* *default*
* *emacs*
* *friendly*
* *fruity*
* *manni*
* *monokai*
* *murphy*
* *native*
* *pastie*
* *perldoc*
* *tango*
* *trac*
* *vim*
* *vs* (Visual Studio colors)


.. note::
    This setting cannot be updated per plugin instance, to avoid a mix of different styles used together.
    The entire site uses a single consistent style.

ECMS_CODE_SHORTLIST
~~~~~~~~~~~~~~~~~~~

The plugin displays a shortlist of popular programming languages in the "Language" selectbox,
since Pygments provides highlighting support for many many programming languages.

This settings allows the shortlist to be customized.

ECMS_CODE_SHORTLIST_ONLY
~~~~~~~~~~~~~~~~~~~~~~~~

Enable this setting to only show the programming languages of the shortlist.
This can be used to simplify the code plugin for end users.
