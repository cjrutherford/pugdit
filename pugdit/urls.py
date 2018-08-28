"""pugdit URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import include, path, re_path
from django.contrib import admin
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.conf import settings
from graphene_django.views import GraphQLView
from django.views.decorators.csrf import csrf_exempt
from revproxy.views import ProxyView

from .postoffice.schema import schema
from .postoffice.views import add_asset


admin.autodiscover()

urlpatterns = [
    path('accounts/', include('allauth.urls')),
    # The following SPA settings are handled in Django-SPA
    # - everything not matched in Django's urlpatterns goes to /
    # - index.html served on /
    # - all /static/... files served on /...
    path('graphql/', csrf_exempt(GraphQLView.as_view(graphiql=True, schema=schema))),
    #TODO big "cross site" scripting security hole
    re_path(r'^ipfs/(?P<path>.*)$', ProxyView.as_view(upstream=settings.IPFS_URL + '/ipfs/')),
    path('api/add-asset/', add_asset),

    # other views still work too
    path('admin/', admin.site.urls),
]

if settings.DEPLOYMENT == 'dev':
  urlpatterns = urlpatterns + static(
      settings.MEDIA_URL,
      document_root=settings.MEDIA_ROOT
  )

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
