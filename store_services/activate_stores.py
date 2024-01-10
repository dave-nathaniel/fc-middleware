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

# activate = ['CALABAR, NDIDEM', 'LAG, AGUNGI', 'LAG, AJAH', 'LAG, AJOSE ADEOGUN', 'LAG, AKOWONJO', 'LAG, ALIMOSHO', 'LAG, AWOLOWO', 'LAG, AWOLOWO 2', 'LAG, BADORE', 'LAG, CONOIL IKEJA', 'LAG, DOMINO E-CENTRE', 'LAG, EJIGBO', 'LAG, EKORO', 'LAG, ENTOURAGE MALL', 'LAG, FESTAC', 'LAG, FREEDOMWAY', 'LAG HEYDEN ALAPERE', 'LAG, IDI-IROKO RD', 'LAG, IDIMU', 'LAG, IKORODU', 'LAG, IKOTUN', 'LAG, ILUPEJU', 'LAG IPAJA ROAD', 'LAG, IRE-AKARI', 'LAG, JIBOWU', 'LAG, JOEL OGUNNAIKE', 'LAG, LATEEF JAKANDE', 'LAG, LEKKI PHASE 1', 'LAG, MOBIL OGBA', 'LAG, OBA AKRAN', 'LAG, OKE-AFA', 'LAG, OKOTA', 'LAG, ONIRU', 'LAG, OPEBI', 'LAG, OSOLOWAY', 'LAG, SKYMALL', 'LAG, TEJUOSHO', 'LAG, TOTAL LEKKI ', 'LAG, VGC', 'PH, DOXA RD', 'AKWA IBOM, AKA RD', 'LAG, BODE THOMAS', 'LAG, MARINA', 'LAG, OGUDU', 'LAG, OMOLE', 'LAG, ETERNA LEKKI', 'LAG, MMA2', 'LAG, GBAGADA', 'LAG, MAGODO', 'LAG, WAREHOUSE RD, APAPA', 'LAG, NNPC ALAPERE', 'LAG, OGUNLANA DRIVE', 'LAG, DIYA STREET', 'LAG, HEYDEN IPAJA', 'LAG, FATGBEMS BERGER', 'LAG, SALOLO', 'LAG, ISAWO-IKORODU', 'LAG, TOTAL ONIGBAGBO']

activate = ['4100017-3', '4100003-38', '4100003-12', '4100003-2', '4100003-18', '4100003-43', '4100003-7', '4100003-8', '4100003-51', '4100003-58', '4100003-27', '4100003-46', '4100003-57', '4100003-1', '4100003-33', '4100003-9', '4100003-50', '4100015-1', '4100003-31', '4100003-30', '4100003-52', '4100003-17', '4100003-49', '4100003-23', '4100003-22', '4100003-40', '4100003-41', '4100003-3', '4100003-47', '4100003-45', '4100003-24', '4100003-35', '4100003-5', '4100003-15', '4100003-34', '4100003-6', '4100003-21', '4100003-44', '4100003-11', '4100008-6', '4100013-4', '4100003-20', '4100003-10', '4100003-36', '4100003-16', '4100003-4', '4100003-19', '4100003-14', '4100003-26', '4100003-25', '4100003-29', '4100003-28', '4100003-39', '4100003-53', '4100003-55', '4100003-61', '4100003-59']

# activate = ['LAG, FATGBEMS BERGER']

deactivated_stores = Store.objects.filter(post_sale_to_byd=False)

for item in deactivated_stores:
	item.post_sale_to_byd = item.byd_cost_center_code.strip() in map(lambda x: x.strip(), activate)
	item.save()

activated_stores = Store.objects.filter(post_sale_to_byd=True)
print(f"Activated Stores: \n{chr(10).join(['--> ' + i.icg_warehouse_name for i in activated_stores])}")