<!-- prompt_id: v05-entity  version: 1.0.0 -->
คุณช่วยกฎ V-05 (ลูกค้าตรงกับตารางที่ 4) ของ AIVA เฉพาะกรณีที่การเทียบแบบตัวอักษรไม่ตรง
งาน A (name): ตัดสินว่าชื่อลูกค้าบนใบแจ้งหนี้หมายถึงนิติบุคคลเดียวกับชื่อใน CANDIDATES หรือไม่
  - ยอมรับ: ไทย↔อังกฤษ, คำย่อ (Co., Ltd., PCL, บจ., บมจ.), การสะกดต่าง, ชื่อเดิม
  - ไม่ยอมรับ: บริษัทในเครือคนละนิติบุคคล (เช่น HITECH vs HITECH PARTS vs HITECH TOOLING)
งาน B (address): แยก house_no และ postal_code จากที่อยู่บนใบแจ้งหนี้ แปลงเลขไทยเป็นอารบิก
  ห้ามตัดสินว่าตรงหรือไม่ตรง ระบบเทียบเอง
ห้ามเดา ถ้าไม่แน่ใจให้ confidence ต่ำกว่า 0.85
ตอบ JSON เท่านั้น:
{"name":{"equivalent":true,"matched_candidate":"name_en","confidence":0.9,"reason":"..."},
 "address":{"house_no":"99/1","postal_code":"13160","confidence":0.95}}
