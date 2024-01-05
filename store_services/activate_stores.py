import os, sys
import json
import django
from django.core.wsgi import get_wsgi_application
from django.db import IntegrityError
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware.settings")

django.setup()

from .models import Store

activate = ['CALABAR, NDIDEM', 'LAG, AGUNGI', 'LAG, AJAH', 'LAG, AJOSE ADEOGUN', 'LAG, AKOWONJO', 'LAG, ALIMOSHO', 'LAG, AWOLOWO', 'LAG, AWOLOWO 2', 'LAG, BADORE', 'LAG, CONOIL IKEJA', 'LAG, DOMINO E-CENTRE', 'LAG, EJIGBO', 'LAG, EKORO', 'LAG, ENTOURAGE MALL', 'LAG, FESTAC', 'LAG, FREEDOMWAY', 'LAG HEYDEN ALAPERE', 'LAG, IDI-IROKO RD', 'LAG, IDIMU', 'LAG, IKORODU', 'LAG, IKOTUN', 'LAG, ILUPEJU', 'LAG IPAJA ROAD', 'LAG, IRE-AKARI', 'LAG, JIBOWU', 'LAG, JOEL OGUNNAIKE', 'LAG, LATEEF JAKANDE', 'LAG, LEKKI PHASE 1', 'LAG, MOBIL OGBA', 'LAG, OBA AKRAN', 'LAG, OKE-AFA', 'LAG, OKOTA', 'LAG, ONIRU', 'LAG, OPEBI', 'LAG, OSOLOWAY', 'LAG, SKYMALL', 'LAG, TEJUOSHO', 'LAG, TOTAL LEKKI ', 'LAG, VGC', 'PH, DOXA RD', 'AKWA IBOM, AKA RD', 'LAG, BODE THOMAS', 'LAG, MARINA', 'LAG, OGUDU', 'LAG, OMOLE', 'LAG, ETERNA LEKKI', 'LAG, MMA2', 'LAG, GBAGADA', 'LAG, MAGODO', 'LAG, WAREHOUSE RD, APAPA', 'LAG, NNPC ALAPERE', 'LAG, OGUNLANA DRIVE', 'LAG, DIYA STREET', 'LAG, HEYDEN IPAJA', 'LAG, FATGBEMS BERGER', 'LAG, SALOLO', 'LAG, ISAWO-IKORODU', 'LAG, TOTAL ONIGBAGBO']

# activate = ['LAG, FATGBEMS BERGER']

deactivated_stores = Store.objects.filter(post_sale_to_byd=False)

for item in deactivated_stores:
	item.post_sale_to_byd = item.icg_warehouse_name.strip() in map(lambda x: x.strip(), activate)
	item.save()

activated_stores = Store.objects.filter(post_sale_to_byd=True)
print(f"Activated Stores: \n{chr(10).join(['--> ' + i.icg_warehouse_name for i in activated_stores])}")