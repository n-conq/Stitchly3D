import logging
import xml.etree.ElementTree as ET
import re

logger = logging.getLogger(__name__)

def import_body_measurements(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    measurements = {}

    body_measurements = root.find('body-measurements')
    if body_measurements is None:
        raise ValueError("No 'body-measurements' element found in XML.")

    for m in body_measurements.findall('m'):
        name = m.attrib.get('name')
        value = m.attrib.get('value')
        if name and value:
            try:
                value_int = int(value)
                measurements[name] = value_int
                # Dynamically set variable in global namespace
                globals()[name] = value_int
            except ValueError:
                logger.warning("Value for %s is not an integer: '%s'", name, value)
    return measurements



