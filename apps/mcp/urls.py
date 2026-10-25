"""Mounted at the site root: the MCP endpoint, the OAuth endpoints under /oauth/, and the
well-known metadata documents Claude reads to find them."""
from django.urls import include, path
from oauth2_provider import views as oauth_views

from . import views
from .oauth import ConsentView, ResourceMetadataView

# django-oauth-toolkit reverses its own views in this namespace (metadata, DCR responses).
oauth_patterns = ([
    path('.well-known/oauth-authorization-server', oauth_views.OAuthServerMetadataView.as_view(),
         name='oauth-server-metadata'),
    path('oauth/authorize/', ConsentView.as_view(), name='authorize'),
    path('oauth/token/', oauth_views.TokenView.as_view(), name='token'),
    path('oauth/revoke_token/', oauth_views.RevokeTokenView.as_view(), name='revoke-token'),
    path('oauth/register/', oauth_views.DynamicClientRegistrationView.as_view(), name='dcr-register'),
    path('oauth/register/<str:client_id>/', oauth_views.DynamicClientRegistrationManagementView.as_view(),
         name='dcr-register-management'),
], 'oauth2_provider')

urlpatterns = [
    path('', include(oauth_patterns)),
    path('mcp', views.mcp_endpoint, name='mcp'),
    path('mcp/', views.mcp_endpoint),
    path('.well-known/oauth-protected-resource', ResourceMetadataView.as_view(), name='mcp_resource_metadata'),
    path('.well-known/oauth-protected-resource/mcp', ResourceMetadataView.as_view()),
    path('security/connected-apps/<str:client_id>/disconnect/', views.disconnect, name='mcp_disconnect'),
]
