from signals.settings.base import *  # noqa

from .zds_vng import *  # noqa

SECRET_KEY = 'insecure'
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
TEST_LOGIN = 'signals.admin@example.com'
SITE_DOMAIN = 'localhost:8000'
INSTALLED_APPS += [  # noqa
    'signals.apps.zds',
]

# Email integration settings
EMAIL_INTEGRATIONS = dict(
    FLEX_HORECA=dict(
        RECIPIENT_LIST=['test@test.com', ],
        APPLICABLE_RULES=dict(
            WEEKDAYS='5,6,7',  # fri, sat, sun
            END_TIME='04:00',  # 04:00 o'clock
        )
    ),
    TOEZICHT_OR_NIEUW_WEST=dict(
        RECIPIENT_LIST=['test@test.com', ],
    ),
    VTH_NIEUW_WEST=dict(
        RECIPIENT_LIST=['test@test.com', ],
    ),
)

FEATURE_FLAGS = {
    'API_VALIDATE_EXTRA_PROPERTIES': True,
    'API_SEARCH_ENABLED': False,
    'SEARCH_BUILD_INDEX': False,

    # Permission feature flags
    'PERMISSION_SIAPERMISSIONS': True,
    'PERMISSION_SPLITPERMISSION': False,
    'PERMISSION_SIGNALCREATEINITIALPERMISSION': False,
    'PERMISSION_SIGNALCREATENOTEPERMISSION': False,
    'PERMISSION_SIGNALCHANGESTATUSPERMISSION': False,
    'PERMISSION_SIGNALCHANGECATEGORYPERMISSION': False,

    # Departments permission
    'PERMISSION_DEPARTMENTS': False,
}
