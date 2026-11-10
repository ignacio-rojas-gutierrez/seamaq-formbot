from dataclasses import dataclass

import rto

"""
There can only be a limited number of RTO Planilla - for example, 20 -. The operating principle is a pointer will point to the newest RTO Planilla
over a limited size array. This means upon reaching the end of the array, the pointer will jump onto the first element, overriding it.
"""


@dataclass
class ListaPlanillas:
    rtos : list[rto.RTO] = []
    pointer : int = 0
    array_size = 20