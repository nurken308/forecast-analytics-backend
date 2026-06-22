import pandas as pd
from db.oracle import engine
from datetime import datetime

SEGMENT_FILTERS = {
    "retail": {
        "column": "Segment1",
        "value": "4.Розница",
    },
    "mass": {
        "column": "Segment1",
        "value": "3.Масс продукты",
    },
    "bk_vkl": {
        "column": "Segment2",
        "value": "2.2.БК+ВКЛ",
    },
}



def get_last_month_end():
    today = datetime.today()
    first_day = today.replace(day=1)
    last_day_prev = first_day - pd.Timedelta(days=1)
    return last_day_prev.strftime("%Y%m%d")

def load_oracle_pivot(segment_id: str):
    if segment_id not in SEGMENT_FILTERS:
        raise ValueError(f"Unknown segment_id: {segment_id}")

    filter_info = SEGMENT_FILTERS[segment_id]
    day = get_last_month_end()

    query = f"""

/* +parallel(4) */  -- ускоряет чтение в 4 потока

with miras_pre as (
  select 
    t.base_ymd, t.dvsn_nm, t.ptflo_blng,
    
    -- вычисляем сегменты 1 раз
    case 
      when t.loan_indx_num in ('01','02','09') and t.corp_scal_dstic_cd in ('LARGE','TNKNK') then 'КОРП'
      when t.loan_indx_num in ('01','02','09') and t.corp_scal_dstic_cd not in ('LARGE','TNKNK','SMALL','MICRO') then 'СБ'
      when t.loan_indx_num in ('01','02','09') and t.corp_scal_dstic_cd in ('SMALL','MICRO') then 'МБ'
      when ((t.loan_indx_num in ('03','05','06') and t.loan_sourc_rcd in ('002','003','005')) 
            and t.loan_pgm_num != '0.201.2.1000') then 'ИП+ФЛЕБРР'
      else 'ФЛ'
    end as segm,

    -- классификация продуктов 
    case
     when t.acctg_cdval like '13%' then 'Межбанки'  
        
     when t.acctg_cdval like '1407%' or t.acctg_cdval like '1409%' then 'Факторинг'
       
     when t.loan_pgm_num in ('0.208.046') then 'BCC-BLACK'     
        
     when (t.loan_indx_num = '05') 
     and (t.loan_pgm_num in 
    ('0.201.1.0312',
     '0.201.1.0313',
     '0.201.1.0314',
     '0.201.1.0315',
     '0.201.1.0317',
     '0.201.1.0318',
     '0.201.3.2001',
     '0.201.3.2002',
     '0.201.3.2003',
     '0.201.3.2004',
     '0.201.3.2005',
     '0.201.3.2006',
     '0.201.3.2007',
     '0.201.3.2008',
     '0.205.6.01',
     '0.201.3.20',
     '0.202.8',
     '0.201.1.0316',
     '0.201.1.1801',
     '0.201.1.1802',
     '0.201.1.1803',
     '0.201.1.1804',
     '0.207.9',
     '0.207.901.01',
     '0.207.901.02',
     '1.2.5',
     '0.205.6',
     '0.201.1.17',
     '0.201.1.0312',
     '0.201.1.0313',
     '0.201.1.0314',
     '0.201.1.1816',
     '0.201.1.1818',
     '0.201.1.1805',
     '0.201.1.1806',
     '0.201.1.1807',
     '0.201.1.1808',
     '0.201.1.1809',
     '0.201.1.1810',
     '0.201.1.1811')) then 'Беззалоговые_Альфа' 

     when t.loan_pgm_num in 
     ('0.201.1.1131',
      '0.201.1.1132',
      '0.201.1.1133',
      '0.201.1.1134',
      '0.201.1.1136') then '#ипотека'
      
     when t.loan_pgm_num in 
    ('0.201.1.1506') 
     then '#залоговый кредит'
       
     when t.loan_pgm_num in 
    ('0.201.2.1000',
     '0.201.2.1002',
     '0.201.2.1003',
     '0.201.2.1102',
     '0.201.2.1104',
     '0.201.2.1111',
     '0.201.2.1122')
     then 'РБ БЗ ИП'
       
     when t.loan_pgm_num in
    ('0.203.3.0101',
     '0.203.3.0102',
     '0.201.3.2201')
     then 'КЛС'
  
     when t.loan_pgm_num in 
    ('0.201.2.1120',
     '0.201.2.1117',
     '0.201.3.1417',
     '0.201.3.1418')
     and t.cust_type_nm != 'ЮЛ'
     then 'РБ ЗАЛОГОВЫЙ ИП (с)'
       
      when t.loan_pgm_num in 
    ('0.201.2.1120',
     '0.201.2.1117',
     '0.201.3.1417',
     '0.201.3.1418')
     and t.cust_type_nm = 'ЮЛ'
     then 'РБ ЗАЛОГОВЫЙ ТОО (с)'
          
     when t.loan_pgm_num in 
    ('0.201.2.1101',
    '0.201.2.1103',
    '0.201.2.1109',
    '0.201.3.1401',
    '0.201.3.1403',
    '0.201.3.1409',
    '0.201.2.1105',
    '0.201.2.1107',
    '0.201.2.1110',
    '0.201.3.1405',
    '0.201.3.1407',
    '0.201.3.1410',
    '0.201.2.1116',
    '0.201.2.1114',
    '0.210.1.0281',
    '0.210.1.0282',
    '0.210.1.0273',
    '0.210.1.0277',
    '0.210.1.0281',
    '0.210.1.0274',
    '0.210.1.0278',
    '0.210.1.0282',
    '0.210.2.0291',
    '0.210.2.0293',
    '0.210.2.0295',
    '0.210.2.0290',
    '0.210.2.0292',
    '0.210.2.0294',
    '0.201.3.1414',
    '0.201.3.1415',
    '0.201.3.1416',
    '0.201.2.1115',
    '0.201.3.1419',
    '0.201.2.1123',
    '0.210.1.0316',
    '0.201.2.1124',
    '0.201.3.1420',
    '0.210.2.0607',
    '0.201.3.1421',
    '0.201.2.1125') 
     and t.cust_type_nm != 'ЮЛ'
     then 'РБ ЗАЛОГОВЫЙ ИП'
   
   when t.loan_pgm_num in 
    ('0.201.2.1101',
    '0.201.2.1103',
    '0.201.2.1109',
    '0.201.3.1401',
    '0.201.3.1403',
    '0.201.3.1409',
    '0.201.2.1105',
    '0.201.2.1107',
    '0.201.2.1110',
    '0.201.3.1405',
    '0.201.3.1407',
    '0.201.3.1410',
    '0.201.2.1116',
    '0.201.2.1114',
    '0.210.1.0281',
    '0.210.1.0282',
    '0.210.1.0273',
    '0.210.1.0277',
    '0.210.1.0281',
    '0.210.1.0274',
    '0.210.1.0278',
    '0.210.1.0282',
    '0.210.2.0291',
    '0.210.2.0293',
    '0.210.2.0295',
    '0.210.2.0290',
    '0.210.2.0292',
    '0.210.2.0294',
    '0.201.3.1414',
    '0.201.3.1415',
    '0.201.3.1416',
    '0.201.2.1115',
    '0.201.3.1419',
    '0.201.2.1123',
    '0.210.1.0316',
    '0.201.2.1124',
    '0.201.3.1420',
    '0.210.2.0607',
    '0.201.3.1421',
    '0.201.2.1125') 
     and t.cust_type_nm = 'ЮЛ'
     then 'РБ ЗАЛОГОВЫЙ ТОО'
   
     when t.loan_pgm_num in 
    ('0.201.3.1001',
     '0.201.3.1002',
     '0.201.2.0901',
     '0.201.2.0902',
     '0.201.3.1003',
     '0.201.2.0903') 
     then 'ОВЕРДРАФТ'
    
     when t.loan_pgm_num in
    ('0.210.1.0272',
     '0.201.3.0118',
     '0.201.2.0122',
     '0.210.1.0308',
     '0.201.3.0738',
     '0.201.2.0733',
     '0.210.1.0309',
     '0.201.3.0626',
     '0.201.2.0321',
     '0.201.3.0738')
     then 'ФД'
       
     when t.loan_pgm_num in
    ('0.201.3.0119',
     '0.201.2.0120',
     '0.201.3.0740',
     '0.201.2.0735',
     '0.201.3.0628',
     '0.201.2.0323')
     then 'ФЗЗ'
     
   
     when t.loan_pgm_num in 
    ('0.201.3.1402',
     '0.201.3.1404',
     '0.201.3.1411',
     '0.201.3.1413') then 'РБ БЗ ТОО'
    
     when t.loan_pgm_num in 
    ('0.201.3.16',
     '0.201.3.1601',
     '0.201.3.1602',
     '0.201.3.1603',
     '0.201.3.1604',
     '0.210.2.0606',
     '0.201.3.1609',
     '0.201.2.1209',
     '0.201.3.1605',
     '0.201.2.12',
     '0.201.2.1201',
     '0.201.2.1202',
     '0.201.2.1203',
     '0.201.2.1204',
     '0.201.2.1205')
     then 'БК'
   
     when t.loan_pgm_num in 
    ('0.201.2.12',
     '0.201.3.16',
     '0.201.2.1206',
     '0.201.2.1207',
     '0.201.2.1208',
     '0.201.3.1606',
     '0.201.3.1607',
     '0.210.1.0315',
     '0.201.3.1610',
     '0.201.2.1210',
     '0.201.3.1608')
     then 'ВКЛ'
       
     when t.loan_pgm_num in 
    ( '0.201.3.1701',
      '0.201.3.1702',
      '0.201.3.1703',
      '0.210.2.0284',
      '0.210.2.0286',
      '0.210.2.0288',
      '0.201.2.1301',
      '0.201.2.1302',
      '0.201.2.1303',
      '0.210.2.0285',
      '0.210.2.0287',
      '0.210.2.0289',
      '0.201.3.1801',
      '0.201.3.1802',
      '0.201.3.1803',
      '0.210.1.0296',
      '0.210.1.0298',
      '0.210.1.0300',
      '0.201.3.1804',
      '0.210.1.0306',
      '0.201.2.1401',
      '0.201.2.1402',
      '0.201.2.1403',
      '0.210.1.0297',
      '0.210.1.0299',
      '0.210.1.0301',
      '0.201.2.1404',
      '0.210.2.0601',
      '0.210.2.0602',
      '0.210.2.0603',
      '0.201.5.0101',
      '0.201.5.0102',
      '0.201.5.0201',
      '0.201.5.0202',
      '0.210.1.0401',
      '0.210.2.0401',
      '0.201.3.1704',
      '0.201.2.1304',
      '0.201.3.1805',
      '0.201.2.1405',
      '0.210.2.0604',
      '0.210.1.0314',
      '0.210.2.0605',
      '0.201.3.2101',
      '0.201.3.2102',
      '0.201.3.2103',
      '0.201.3.2104',
      '0.201.2.1701',
      '0.201.2.1702',
      '0.201.2.1703',
      '0.201.2.1704',
      '0.210.2.0301',
      '0.210.2.0302',
      '0.210.2.0303',
      '0.210.2.0304',
      '0.210.2.0305',
      '0.210.2.0306',
      '0.210.2.0307',
      '0.210.2.0308',
      '0.210.2.0309',
      '0.210.2.0310',
      '0.210.2.0311',
      '0.210.2.0312',
      '0.210.2.0313',
      '0.210.2.0314')
     and (((t.loan_indx_num = '03') or ((t.loan_indx_num = '05' or t.loan_indx_num = '06') 
     and (t.loan_sourc_rcd = '002' or t.loan_sourc_rcd = '003' or t.loan_sourc_rcd = '005')) 
     and t.loan_pgm_num != '0.201.2.1000')) then 'ИП+ФЛЕБРР'
     
      when t.loan_pgm_num in 
    ('0.201.3.1701',
      '0.201.3.1702',
      '0.201.3.1703',
      '0.210.2.0284',
      '0.210.2.0286',
      '0.210.2.0288',
      '0.201.2.1301',
      '0.201.2.1302',
      '0.201.2.1303',
      '0.210.2.0285',
      '0.210.2.0287',
      '0.210.2.0289',
      '0.201.3.1801',
      '0.201.3.1802',
      '0.201.3.1803',
      '0.210.1.0296',
      '0.210.1.0298',
      '0.210.1.0300',
      '0.201.3.1804',
      '0.210.1.0306',
      '0.201.2.1401',
      '0.201.2.1402',
      '0.201.2.1403',
      '0.210.1.0297',
      '0.210.1.0299',
      '0.210.1.0301',
      '0.201.2.1404',
      '0.210.2.0601',
      '0.210.2.0602',
      '0.210.2.0603',
      '0.201.5.0101',
      '0.201.5.0102',
      '0.201.5.0201',
      '0.201.5.0202',
      '0.210.1.0401',
      '0.210.2.0401',
      '0.201.3.1704',
      '0.201.2.1304',
      '0.201.3.1805',
      '0.201.2.1405',
      '0.210.2.0604',
      '0.210.1.0314',
      '0.210.2.0605',
      '0.201.3.2101',
      '0.201.3.2102',
      '0.201.3.2103',
      '0.201.3.2104',
      '0.201.2.1701',
      '0.201.2.1702',
      '0.201.2.1703',
      '0.201.2.1704',
      '0.210.2.0301',
      '0.210.2.0302',
      '0.210.2.0303',
      '0.210.2.0304',
      '0.210.2.0305',
      '0.210.2.0306',
      '0.210.2.0307',
      '0.210.2.0308',
      '0.210.2.0309',
      '0.210.2.0310',
      '0.210.2.0311',
      '0.210.2.0312',
      '0.210.2.0313',
      '0.210.2.0314')
      and (t.loan_indx_num = '01' or t.loan_indx_num = '02' or t.loan_indx_num = '09') 
      and t.corp_scal_dstic_cd  in ('SMALL', 'MICRO')
      then 'МБ'
     
    
     when t.loan_pgm_num in 
    ('0.210.',
     '0.210.2.0278',
     '0.210.2.0279',
     '0.210.2.0280',
     '0.210.2.0281',
     '0.210.2.0282',
     '0.210.2.0283',
     '0.210.1.0294',
     '0.210.1.0295',
     '0.210.1.0302',
     '0.210.1.0303',
     '0.210.1.0304',
     '0.210.1.0305')
     then 'Кредитные_линии'
     
     when (t.loan_indx_num = '01' or t.loan_indx_num = '02' or t.loan_indx_num = '09') and t.corp_scal_dstic_cd in ('LARGE', 'TNKNK')   
     then 'КОРП'
    
     when (t.loan_indx_num = '01' or t.loan_indx_num = '02' or t.loan_indx_num = '09') and t.corp_scal_dstic_cd not in ('LARGE', 'SMALL', 'MICRO', 'TNKNK')
     then 'СБ'
    
     when (t.loan_indx_num = '01' or t.loan_indx_num = '02' or t.loan_indx_num = '09') and t.corp_scal_dstic_cd  in ('SMALL', 'MICRO')
     then 'Прочие МБ'
     
     when (((t.loan_indx_num = '03') or ((t.loan_indx_num = '05' or t.loan_indx_num = '06') 
     and (t.loan_sourc_rcd = '002' or t.loan_sourc_rcd = '003' or t.loan_sourc_rcd = '005')) 
     and t.loan_pgm_num != '0.201.2.1000')) then 'Прочие ИП+ФЛЕБРР'
     
     when t.loan_pgm_num in 
    ('0.201.1.1120',
     '0.201.1.1121',
     '0.201.1.1123',
     '0.201.1.1124',
     '0.201.1.1125',
     '0.201.1.1129',
     '0.201.1.1130',
     '0.201.1.1135') then 'Баспана'
    
     when t.loan_pgm_num in 
    ('0.201.1.1143',
     '0.201.1.1142') then 'Jana ипотека'
     
    
     when (t.loan_indx_num = '06' or t.loan_indx_num = '08') 
     and (t.loan_sourc_rcd <> '002' 
     and t.loan_sourc_rcd <> '003' 
     and t.loan_sourc_rcd <> '005') then 'Прочая ипотека' 
    
     when t.loan_indx_num = '05' and (t.loan_pgm_num in
    ('0.201.1.1606',
     '0.201.1.1603',
     '0.201.1.1605',
     '0.201.1.1611',
     '0.201.1.0505',
     '0.201.1.0506',
     '0.201.1.0512')) then 'Льготное автокредит-е' 
       
     when ((t.loan_indx_num = '05') 
     and (t.loan_sourc_rcd <> '002' 
     and t.loan_sourc_rcd <> '003' 
     and t.loan_sourc_rcd <> '005') 
     and (t.loan_objct_num = '152')) 
     and (t.loan_pgm_num not in
    ('0.201.1.1606',
     '0.201.1.1603',
     '0.201.1.1605',
     '0.201.1.1611',
     '0.201.1.0505',
     '0.201.1.0506',
     '0.201.1.0512',
     '0.201.1.0521',
     '0.201.1.0522')) then 'Коммерческое автокредит-е'   
      
     when t.acctg_cdval like '1461%' then 'ОБРАТНОЕ РЕПО'
       
     when (t.loan_indx_num = '05') and (t.loan_pgm_num in ('0.201.1.0727','0.201.1.0719','0.201.1.0750')) then 'Вн. реф-ие БЗ'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.201.1.0749') then 'Прочие беззалоги'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.201.1.0307') then 'Наличные под зарплату'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num in ('0.201.1.0308', '0.201.1.0311')) then 'Прочие беззалоги'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.041') then 'Прочие карты'  
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.021') then 'Прочие карты'  
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.042') then 'Прочие карты'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.034') then 'Прочие карты'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.031') then 'Прочие карты'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.033') then 'Прочие карты'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.032') then 'Прочие карты'      
     when (t.loan_indx_num = '05') and (t.loan_pgm_num = '0.208.047') then 'Прочие карты' 
     when (t.loan_indx_num = '05') and (t.loan_pgm_num in ('0.208.043', '0.208.044', '0.201.1.0310')) then '#картакарта'      
     when (t.loan_indx_num = '05') and (t.loan_pgm_num in ('0.201.1.0324')) then 'Прочие беззалоги' 
     when (t.loan_indx_num = '05') and (t.loan_pgm_num in ('0.201.1.0321')) then 'Кредит наличными ePIL'
     when (t.loan_indx_num = '05') and (t.loan_pgm_num in ('0.201.1.0322','0.201.1.0320')) then 'Рассрочка ePOS' 
     when (t.loan_indx_num = '05') and (t.loan_pgm_num in ('0.201.1.0747')) then 'Реф. проблемных БЗ'
     else 'Потреб. прочие'
     end as Products,

    /* агрегируемые поля */
    (nvl(t.prcpl_kp_amt,0) + nvl(t.ovrdu_prcpl_kp_amt,0) + nvl(t.indx_prcpl_kp_amt,0))/1e6 as OD,
    
    (nvl(t.int_kp_amt,0) + nvl(t.ovrdu_kp_int,0))/1e6 as procenty,
    
    case when t.ovrdu_prod_val_new not in ('Без просрочки') 
         then (nvl(t.prcpl_kp_amt,0)+nvl(t.ovrdu_prcpl_kp_amt,0)+nvl(t.indx_prcpl_kp_amt,0))/1e6 else 0 end as Prosrochka_1_plus,
           
    case when t.ovrdu_prod_val_new not in ('Без просрочки','1-15 дней','16-30 дней') 
         then (nvl(t.prcpl_kp_amt,0)+nvl(t.ovrdu_prcpl_kp_amt,0)+nvl(t.indx_prcpl_kp_amt,0))/1e6 else 0 end as Prosrochka_30_plus,
           
    case when t.ovrdu_prod_val_new not in ('Без просрочки','1-15 дней','16-30 дней','31-60 дней','61-90 дней')
         then (nvl(t.prcpl_kp_amt,0)+nvl(t.ovrdu_prcpl_kp_amt,0)+nvl(t.indx_prcpl_kp_amt,0))/1e6 else 0 end as NPL,
           
    case when t.ovrdu_prod_val_new in ('61-90 дней')
         then (nvl(t.prcpl_kp_amt,0) + nvl(t.ovrdu_prcpl_kp_amt,0) + nvl(t.indx_prcpl_kp_amt,0))/1000000 
         else 0 end as Prosrochka_61_90,     
         
           
    (nvl(t.prvs_kzt_amt,0)+nvl(t.indt_prvs_amt,0)+nvl(t.indt_not_prvs_amt,0))/1e6 as provisii,
    
    case when t.bskt_val='3' 
         then (nvl(t.prcpl_kp_amt,0)+nvl(t.ovrdu_prcpl_kp_amt,0)+nvl(t.indx_prcpl_kp_amt,0)+nvl(t.int_kp_amt,0)+nvl(t.ovrdu_kp_int,0))/1e6 else 0 end as korzina3,
           
    case when t.loan_ctrc_cd_num != '0' then 1 else 0 end as zaimy,
      
    (nvl(t.prcpl_kp_amt,0)+nvl(t.ovrdu_prcpl_kp_amt,0)+nvl(t.indx_prcpl_kp_amt,0)+nvl(t.int_kp_amt,0)+nvl(t.ovrdu_kp_int,0)+nvl(t.preum_ccy,0)-nvl(t.dscnt_amt,0))/1e6 as Zadolzhenost
   
   
---------------------------------------------------------------------------------------------------------------------
    
     from trdlc0010s t
          WHERE t.base_ymd =: day ---Дата
          
          and t.data_dstic_cd in (      '1','2','3'            )
          
          ------------     '1','2','3' 
),

---------------------------------------------------------------------------------------------------------------------
miras as (
  select 
    base_ymd,
    dvsn_nm,
    segm,
    ptflo_blng,
    Products,
    OD,
    procenty,
    Prosrochka_1_plus,
    Prosrochka_30_plus,
    Prosrochka_61_90,
    NPL,
    provisii,
    korzina3,
    zaimy,
    Zadolzhenost,
    case 
      when Products in ('СБ','КОРП') then '1.КБ+СБ'
      when Products in ('Факторинг','МБ','ИП+ФЛЕБРР','Прочие ИП+ФЛЕБРР','БК','Прочие МБ','ВКЛ') then '2.МБ'
      when Products in ('КЛС',
      'ОВЕРДРАФТ',
      'РБ БЗ ИП',
      'РБ БЗ ТОО',
      'РБ ЗАЛОГОВЫЙ ИП (с)',
      'РБ ЗАЛОГОВЫЙ ТОО (с)',
      'РБ ЗАЛОГОВЫЙ ИП',
      'РБ ЗАЛОГОВЫЙ ТОО',
      'ФД', 'ФЗЗ') then '3.Масс продукты'
      when Products = 'Межбанки' then 'Межбанки'
      when Products = 'ОБРАТНОЕ РЕПО' then 'ОБРАТНОЕ РЕПО'
      when Products = 'Кредитные_линии' then 'Кредитные_линии'        
      else '4.Розница'
    end as Segment1,
    
    
    case
      when Products = 'КОРП' then '1.1.КБ'
      when Products = 'СБ' then '1.2.СБ'
      when Products in ('МБ', 'Прочие МБ') then '2.1.МБ'
      when Products in ('БК', 'ВКЛ') then '2.2.БК+ВКЛ'
      when Products in ('ИП+ФЛЕБРР', 'Прочие ИП+ФЛЕБРР') then '2.3.ИП+ФЛЕБРР'
      when Products in ('Факторинг') then '2.4.Факторинг'      
      when Products in 
      ('РБ ЗАЛОГОВЫЙ ТОО (с)',
       'РБ ЗАЛОГОВЫЙ ИП (с)',
       'РБ БЗ ИП',
       'ОВЕРДРАФТ',
       'КЛС',
       'РБ БЗ ТОО') then '3.1.Скоринг'
       
      when Products in 
      ('РБ ЗАЛОГОВЫЙ ИП',
       'РБ ЗАЛОГОВЫЙ ТОО' ) then '3.2.КК'
       
      when Products in 
      ('ФД',
       'ФЗЗ') then '3.3.Финансирование дистрибьютеров'
       
      when Products = 'Межбанки' then 'Межбанки'
      when Products = 'ОБРАТНОЕ РЕПО' then 'ОБРАТНОЕ РЕПО'
      when Products = 'Кредитные_линии' then 'Кредитные_линии'
        
      when Products in 
      ('#залоговый кредит',
       'Потребительские прочие') then '4.2.Потребы'
      
      when Products in
      ('Коммерческое автокредитование',
       'Льготное автокредитование') then '4.3.Авто'
      
      when Products in
       ('#ипотека',
        'Прочая ипотека',
        'Jana ипотека',
        'Баспана') then '4.1.Ипотека'
     
      when Products in
       ('Карта-карта',
        'BCC-BLACK',
        'Прочие кредитные карты') then '4.5.Кредитные карты'  
      
      else '4.4.Беззалог'
    end as Segment2
    
    
  from miras_pre
)


---------------------------------------------------------------------------------------------------------------------
SELECT
    m.base_ymd,
    SUM(m.OD) AS od,
    SUM(m.Prosrochka_1_plus) AS prosrochka_1
FROM miras m
WHERE m.{filter_info["column"]} = :segment_value
GROUP BY m.base_ymd
ORDER BY m.base_ymd
    """

    df = pd.read_sql(
        query,
        engine,
        params={
            "segment_value": filter_info["value"],
            "day": day,
        },
    )

    return df