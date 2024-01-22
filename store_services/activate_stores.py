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

# activate = ['B2', 'B3', 'B1', 'B0', 'B4', 'V0', 'VC', 'V3', 'VH', 'VB', 'VF', 'V9', 'V7', 'VE', 'V5', 'VI', 'VD', 'V4', 'VG', 'V8', 'V2', 'M2', 'M1', 'M4', 'B5', 'B6', 'M7', 'M8', 'M6', '00', 'M9', 'MA', 'MC', 'MD', 'MB', 'B8', 'MH', 'MI', 'MJ', 'BC', 'B9', 'BA', 'BB', 'QD', 'QA', 'QB', 'Q9', 'QC', '03', 'BG', 'VL', 'VN', 'VO', 'VK', 'VR', 'VV', 'VT', 'VQ', 'J5', 'I3', 'I4', 'I5', 'J6', 'I6', 'IT', 'JE', 'JI', 'I8', 'J8', 'JK', 'IL', 'II', 'IZ', 'J4', 'J9', 'IU', 'IY', 'JB', 'I0', 'JC', 'I9', 'IA', 'J7', 'J1', 'IB', 'I2', 'J3', 'IE', 'JO', 'IO', 'IG', 'IX', 'IS', 'IN', 'JG', 'IM', 'VY', 'VX', 'VW', 'VZ', 'Q3', 'Q6', 'MK', 'N0', 'MP', 'MW', 'N1', 'MY', 'MX', 'MS', 'ML', 'MU', 'MM', 'MZ', 'MR', 'X1', 'M3', 'I7', 'IC', 'ID', 'IF', 'Z0', 'Z1', '01', '02', '04', '05', '06', 'V6', 'VA', 'VJ', 'VM', 'VP', 'VS', 'X0', 'B7', 'BD', 'BE', 'BF', 'M0', 'M5', 'ME', 'MF', 'MG', 'MN', 'MO', 'MQ', 'MV', 'I1', 'IH', 'IK', 'IQ', 'IR', 'IV', 'IW', 'J2', 'JA', 'JD', 'JH', 'JJ', 'Q1', 'Q2', 'Q4', 'Q5', 'Q7', 'Q8', 'QE', 'MT']

activate = ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "BA", "BB", "BC", "BD", "BE", "BF", "BG", "M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "MA", "MB", "MC", "MD", "ME", "MF", "MG", "MH", "MI", "MJ", "MK", "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "N0", "N1", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "QA", "QB", "QC", "QD", "QE"]

# activated_stores = Store.objects.filter(post_sale_to_byd=True)
# activated_stores = [x.icg_warehouse_name for x in activated_stores]

# for item in activate:
# 	if item not in activated_stores:
# 		print(item)

# sys.exit()

deactivated_stores = Store.objects.filter(post_sale_to_byd=False)

for item in deactivated_stores:
	item.post_sale_to_byd = item.icg_warehouse_code.strip() in map(lambda x: x.strip(), activate)
	item.save()

activated_stores = Store.objects.filter(post_sale_to_byd=True)
print([i.icg_warehouse_code for i in activated_stores])
# print(f"Activated Stores: \n{chr(10).join(['--> ' + i.icg_warehouse_name for i in activated_stores])}")
print(f"{len(activated_stores)} activated stores.")