import os
import sys

from django.conf import settings


sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), settings.BLENDER_RENDER_TOOLS_DIR))
