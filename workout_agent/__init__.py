# `adk web` discovers an agent by importing this package and looking for a
# module that exposes `root_agent`. This one line is what makes the folder
# show up in the dev UI's agent dropdown.
from . import agent
