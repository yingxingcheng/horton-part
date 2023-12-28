# HORTON-PART: molecular density partition schemes based on HORTON package.
# Copyright (C) 2023-2024 The HORTON-PART Development Team
#
# This file is part of HORTON-PART
#
# HORTON-PART is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# HORTON-PART is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>
#
# --
import logging


def deflist(logger: logging.Logger, l: list) -> None:
    """Print a definition list.

    Parameters
    ----------
    logger:
        The logger.
    l : list
        A list of keyword and value pairs. A table will be printed where the first
        column contains the keywords and the second column contains (wrapped) values.
    """
    widest = max(len(item[0]) for item in l)
    for name, value in l:
        logger.info(f"  {name.ljust(widest)} : {value}")
