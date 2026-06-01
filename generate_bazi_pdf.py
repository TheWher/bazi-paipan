#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成八字命理分析PDF报告。所有排盘数据由bazi_calculator精确计算。"""

from fpdf import FPDF
from bazi_calculator import paipan, DI_ZHI, CANG_GAN
import os


class BaziPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        font_dir = r'C:\Windows\Fonts'
        self.add_font('Song', '', os.path.join(font_dir, 'simsun.ttc'), uni=True)
        self.add_font('Hei', '', os.path.join(font_dir, 'simhei.ttf'), uni=True)
        self.add_font('Kai', '', os.path.join(font_dir, 'simkai.ttf'), uni=True)
        self.add_font('Fang', '', os.path.join(font_dir, 'simfang.ttf'), uni=True)
        self.set_auto_page_break(True, 20)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('Fang', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 5, '八字命理分析报告', align='C')
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font('Fang', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'第 {self.page_no()} 页', align='C')

    def cover_page(self, birth_str, gender, location, plate_date):
        self.add_page()
        self.ln(40)
        self.set_font('Hei', '', 36)
        self.set_text_color(30, 30, 30)
        self.cell(0, 15, '八字命理分析报告', align='C')
        self.ln(22)
        self.set_draw_color(80, 80, 80)
        self.set_line_width(0.5)
        x = self.get_x() + 30
        self.line(x, self.get_y(), self.w - x, self.get_y())
        self.ln(15)
        self.set_font('Kai', '', 14)
        self.set_text_color(60, 60, 60)
        for line in [
            f'出生日期：{birth_str}',
            f'性    别：{gender}',
            f'出生地点：{location}',
            f'排盘日期：{plate_date}',
        ]:
            self.cell(0, 12, line, align='C')
            self.ln(12)
        self.ln(10)
        self.set_draw_color(80, 80, 80)
        self.line(x, self.get_y(), self.w - x, self.get_y())

    def section_title(self, title):
        self.ln(5)
        self.set_font('Hei', '', 16)
        self.set_text_color(20, 60, 120)
        self.cell(0, 10, title)
        self.ln(12)
        self.set_draw_color(20, 60, 120)
        self.set_line_width(0.8)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def sub_title(self, title):
        self.ln(3)
        self.set_font('Hei', '', 12)
        self.set_text_color(40, 40, 40)
        self.cell(0, 8, title)
        self.ln(10)

    def body_text(self, text):
        self.set_font('Song', '', 10.5)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 6.5, text, align='L')
        self.ln(1)

    def table_row(self, cells, widths, header=False):
        if header:
            self.set_font('Hei', '', 9)
        else:
            self.set_font('Song', '', 9)
        self.set_fill_color(245, 245, 250) if header else self.set_fill_color(255, 255, 255)
        max_h = 6
        for i, (cell, w) in enumerate(zip(cells, widths)):
            if i == 0 and header:
                self.set_text_color(20, 60, 120)
            else:
                self.set_text_color(50, 50, 50)
            self.cell(w, max_h, cell, border=1, fill=True)
        self.ln()


# ============================================================
# 分析文本生成 (Interpretive content)
# ============================================================

def _canggan_str(zhi):
    items = CANG_GAN.get(zhi, [])
    return '/'.join(f'{g}' for g, _ in items)


SHICHEN = {0: '子时', 1: '丑时', 2: '寅时', 3: '卯时', 4: '辰时',
           5: '巳时', 6: '午时', 7: '未时', 8: '申时', 9: '酉时',
           10: '戌时', 11: '亥时'}


def build_pdf(birth_year=2005, birth_month=8, birth_day=19,
              birth_hour=1, birth_minute=35,
              gender='男', longitude=113.75, location='广东省东莞市'):
    """生成八字命理分析PDF报告。所有排盘数据由bazi_calculator精确计算。"""

    # ===== 精确排盘 =====
    plate = paipan(birth_year, birth_month, birth_day, birth_hour, birth_minute,
                   gender, longitude, location)
    s = plate.sizhu
    qy = plate.qiyun
    du = plate.dayun
    kong = plate.kongwang

    ri_gan = s['day']['gan']
    ri_zhi = s['day']['zhi']
    yue_zhi = s['month']['zhi']
    shi_zhi = s['hour']['zhi']
    shi_idx = DI_ZHI.index(shi_zhi)
    shichen = SHICHEN.get(shi_idx, f'{shi_zhi}时')

    qiyun_age = qy['qiyun_age']
    qiyun_year = int(qy['qiyun_year']) + 1  # 交运年份

    current_age_2026 = 2026 - birth_year
    current_dayun = None
    for d in du:
        if d['start_age'] <= current_age_2026 < d['end_age']:
            current_dayun = d
            break

    birth_str = f'{birth_year}年{birth_month}月{birth_day}日 {birth_hour:02d}:{birth_minute:02d}（{shichen}）'
    lunar_y = plate.lunar['year']
    lunar_m = plate.lunar['month']
    lunar_d = plate.lunar['day']
    lunar_str = f'{plate.year_type[0]}历{lunar_y}年{lunar_m}月{lunar_d}日{shichen}'
    solar = plate.solar_adjusted

    pdf = BaziPDF()

    # ===== 封面 =====
    pdf.cover_page(birth_str, gender, location, '2026年5月27日')

    # ===== 第一部分：命盘综述 =====
    pdf.add_page()
    pdf.section_title('第一部分：命盘综述')

    pdf.sub_title('1.1 八字命盘')
    pdf.body_text(f'公历：{birth_str}')
    pdf.body_text(f'农历：{lunar_str}')
    pdf.body_text(f'性别：{gender}    出生地：{location}    经度：约{longitude}E')
    pdf.body_text(f'真太阳时校正：约{solar["adjusted_hour"]:.1f}时（校正{solar["correction_minutes"]:.0f}min）')

    pdf.ln(3)
    pdf.sub_title('1.2 四柱干支')
    ss = plate.shishen
    pdf.table_row(['', '年柱', '月柱', '日柱', '时柱'], [24, 36, 36, 36, 36], header=True)
    pdf.table_row(['天干', f'{s["year"]["gan"]}（{ss["year"]}）', f'{s["month"]["gan"]}（{ss["month"]}）',
                   f'{s["day"]["gan"]}（日主）', f'{s["hour"]["gan"]}（{ss["hour"]}）'],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['地支', s['year']['zhi'], s['month']['zhi'],
                   s['day']['zhi'], s['hour']['zhi']],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['纳音', plate.nayin['year'], plate.nayin['month'],
                   plate.nayin['day'], plate.nayin['hour']],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['藏干', _canggan_str(s['year']['zhi']), _canggan_str(s['month']['zhi']),
                   _canggan_str(s['day']['zhi']), _canggan_str(s['hour']['zhi'])],
                  [24, 36, 36, 36, 36])

    pdf.ln(3)
    pdf.sub_title('1.3 核心信息')
    pdf.body_text(f'日主：{ri_gan}木（阴木，花草藤萝之木）')
    pdf.body_text(f'格局：正官格（月令申金主气庚金为正官），官杀混杂，官杀空亡')
    pdf.body_text(f'胎元：{plate.taiyuan}    命宫：{plate.minggong}    身宫：{plate.shengong}')
    # 空亡描述
    kong_pillars = [p for p in ['year', 'month', 'day', 'hour'] if kong['pillars'][p]]
    kong_desc = '、'.join([f'{p}支{s[p]["zhi"]}' for p in kong_pillars])
    pdf.body_text(f'空亡：{ri_gan}{ri_zhi}日属甲戌旬，{kong["kong1"]}{kong["kong2"]}空亡（{kong_desc}）')
    pdf.body_text(f'用神：水（印星）第一优先，木（比劫）第二')
    pdf.body_text(f'忌神：金（官杀）、土（财星）')
    pdf.body_text(f'起运：约{qiyun_age:.1f}岁（{qiyun_year}年立秋后交运），{plate.year_type}男命大运{qy["direction"]}')

    # ===== 第二部分：命局分析 =====
    pdf.add_page()
    pdf.section_title('第二部分：命局分析')

    pdf.sub_title('2.1 格局分析')
    pdf.body_text('月令申，申藏庚金——庚为乙木之正官，格局为正官格。《子平真诠》云："八字用神，专求月令，以日干配月令地支，而生克不同，格局分焉。"月令为提纲，申中庚金正官为本局格局之根基。')
    pdf.body_text('格局有三层瑕疵：')
    pdf.body_text('其一，官杀混杂。年支酉藏辛金七杀，月支申藏庚金正官，时支丑又藏辛金七杀。正官与七杀并见，官杀混杂。《渊海子平》谓"官杀混杂，须知去留舒配"——官杀混杂之人，人生选择多、压力来源复杂、内心常有矛盾权衡。申月正官为体、酉年七杀为混，月令重于年支，故以正官格为主格，七杀为混杂。')
    pdf.body_text(f'其二，官杀空亡。{ri_gan}{ri_zhi}日属甲戌旬，空亡在{kong["kong1"]}{kong["kong2"]}。年支酉（七杀）与月支申（正官）双双落入空亡——这是本局最突出的特征。《滴天髓》论空亡："空者，虚也，实者空之，空者实之，造化之机也。"官杀空亡有三层含义：事业层面，体制内路径多波折，机会看似有门实则虚位；心理层面，压力感大于实际压力，命主自己会放大焦虑；积极面，官杀克身之力因空亡而减半，给了身弱乙木喘息空间。')
    pdf.body_text('其三，官杀藏而不透。天干不见庚辛，官杀全部藏于地支。正官藏而不透，意味着命主心中有规矩、有底线、有事业心，但不擅长外在表现和争取——机会需要大运流年引动才会显现，平时处于潜伏状态。')
    pdf.body_text(f'格局结论：正官格框架仍在（月令申金未破），但格局层次因官杀混杂+空亡而降低。非大富大贵之格，属中人之上的层次。格中有病——官杀混杂为病、空亡为病、藏而不透为病；也有药——{ri_zhi}水正印化官杀生身。此格局需大运扶助才能发挥潜力。')

    pdf.sub_title('2.2 旺衰判断')
    pdf.body_text('得令：乙木生于申月（金旺木囚），不得令。申月庚金当令，金锐克木，日主失时。')
    pdf.body_text(f'得地：日支{ri_zhi}，{ri_zhi}为水、为乙木之正印。乙木在{ri_zhi}按十二长生为"死"地，但{ri_zhi}水能生木，{ri_zhi}中又藏甲木劫财。综合来看，{ri_zhi}对乙木是有生扶之力但不强，属"得气"而非"得根"。')
    pdf.body_text('得势：天干见乙木比肩（年干）、甲木劫财（月干），同类帮扶，得势。但甲木劫财的根在日支亥（亥藏甲），乙木比肩在天干虚浮（酉金截脚）——帮扶之力有，但底气不足。')
    pdf.body_text(f'综合判断：不得令、得势而不强、得地而有限。日主偏弱。弱在金旺克木，幸亏{ri_zhi}水印星贴身通关（申金->{ri_zhi}水->乙木），构成一条脆弱的救应链。《滴天髓》云："能知旺衰之真机，其于三命之奥，思过半矣。"此局身弱的关键在于：弱而不从，有印比帮扶，属正格偏弱，不可论从格。')
    pdf.body_text('身弱的实战意义：喜水（印）生扶、喜木（比劫）帮扶；忌金（官杀）克伐、忌土（财星）再生官杀。身弱正官格，意味着"有规矩之心但缺扛事之力"——需要印比大运来补足。')

    pdf.sub_title('2.3 调候需求')
    pdf.body_text(f'乙木生于申月（孟秋），金神当令，木气凋零。秋月金旺，首要矛盾是金克木，而非寒暖。申月尚有余暑，寒暖并非急务。《穷通宝鉴》论乙木申月："庚金司令，专用己土……或用水印化杀亦可。"调候用神在此局中优先级次于扶抑用神——核心任务是以水化杀、以木扶身，而非调候寒暖。秋金虽凉，{ri_zhi}中壬水不冻，丁火食神在时，寒暖尚可。')
    pdf.body_text('调候结论：非调候优先局。秋月生人，原局亥水润局、丁火暖木，寒暖燥湿基本平衡。')

    # ===== 第三部分：刑冲合害 =====
    pdf.add_page()
    pdf.section_title('第三部分：刑冲合害关系')

    pdf.sub_title(f'3.1 申亥相害（月支申 vs 日支{ri_zhi}）——本局地支核心关系')
    pdf.body_text('申亥相害机制：申中庚金克亥中甲木（庚克甲），亥中壬水泄申中庚金（壬泄庚）。二者互相牵制、互相伤害，但不如六冲那样明显激烈——是一种暗中的、慢性的不协调。')
    pdf.body_text('影响层面：月柱为父母/事业宫，日支为自身/夫妻宫。申亥害意味着原生家庭与自身独立之间存在隐性矛盾（印证了从小学到高中一直寄宿、与父母聚少离多）。月令正官（事业）与日支（自身根基）相害：职业方向上容易"想做的和实际做的有距离"。申为天乙贵人（乙日主贵人在申子），可惜落空亡+被日支所害——贵人缘分有但打了折扣。')

    pdf.sub_title('3.2 酉丑半合（年支酉 vs 时支丑）')
    pdf.body_text('酉丑半合金局，加强七杀之力。年柱（祖上/早年）与晚年（时柱）通过七杀连接——提示家族中或有权威人物影响，或早年经历形成的压力模式会影响晚年格局。但酉在空亡，半合之力打折扣。')

    pdf.sub_title('3.3 申酉会金（月支申 vs 年支酉）')
    pdf.body_text('申酉皆为金，同气相求。但同在空亡中——申酉空亡，金党虽结但力虚。官杀空亡会金，意味着"官杀之势虽成但无力实克"——这是空亡带来的保护效应。')

    pdf.sub_title('3.4 暗合关系')
    pdf.body_text(f'乙庚暗合（日干乙 vs {yue_zhi}中庚）：正官来合身，命主内心深处认同规则、愿意遵守秩序。此合为暗合——外在不一定表现，但内心有准绳。')
    pdf.body_text('甲己暗合（月干甲 vs 丑中己）：劫财合偏财，有求财之心、有竞争意识。但因藏而不透，多半是"想得多做得少"。')
    if current_dayun:
        pdf.body_text(f'午亥暗合（大运/流年午 vs 日支{ri_zhi}）：午中丁己与{ri_zhi}中壬甲暗合。当前大运{current_dayun["gz"]}、流年丙午，午亥暗合引动夫妻宫——暗中有姻缘信号。')

    # ===== 第四部分：神煞 =====
    pdf.section_title('第四部分：神煞速览')
    pdf.body_text('天乙贵人——月支申、日支亥。申空亡贵人助力打折，亥水正印贵人不空、贴身有力，命主一生关键节点必有良师益友相助。')
    pdf.body_text('驿马——日支亥。日坐驿马，一生多动，不宜求"安土重迁"。')
    pdf.body_text('桃花——年支酉。空亡，早年桃花虚浮。')
    pdf.body_text('华盖——时支丑。晚年有精神追求/宗教/玄学缘分。')
    pdf.body_text('文昌——乙日文昌在午，原局无午，大运壬午补上，利学业。')

    # ===== 第五部分：大运走势 =====
    pdf.add_page()
    pdf.section_title('第五部分：大运走势分析')

    pdf.sub_title(f'5.1 大运排盘（{qiyun_age:.1f}岁起运，{qy["direction"]}）')
    pdf.table_row(['步数', '大运', '年龄', '年份', '主题'], [22, 30, 28, 40, 50], header=True)
    dayun_themes = [
        '学业打底，虽非名校但根基尚可',
        '黄金成长期，技术积累 + 情窦初开',
        '事业起飞/压力陡增，伤官合杀化压力为权柄',
        '正官透干，事业进入正轨，财运稳步增长',
        '财坐比劫，中晚年运势优于早年',
        '日主得根，身弱扭转',
        '食伤生财，晚景安宁',
        '水旺扶身，吉祥',
    ]
    for i, d in enumerate(du):
        theme = dayun_themes[i] if i < len(dayun_themes) else ''
        pdf.table_row([f'第{d["step"]}步', d['gz'],
                       f'{d["start_age"]:.0f}-{d["end_age"]:.0f}岁',
                       f'约{d["start_year"]}-{d["end_year"]}年', theme],
                      [22, 30, 28, 40, 50])

    pdf.ln(3)
    if current_dayun:
        cd = current_dayun
        pdf.sub_title(f'5.2 当前大运：{cd["gz"]}运（{cd["start_year"]}-{cd["end_year"]}，{cd["start_age"]:.0f}-{cd["end_age"]:.0f}岁）')
        pdf.body_text(f'壬水正印透干，午火食神坐支。壬水正印化杀生身，是本局最需要的力量。壬水与日支{ri_zhi}水通气呼应——印星有力，大利学业和贵人运。正印主学历、靠山、稳定性。在此运中上了大学。')
        pdf.body_text(f'地支午火与全局互动丰富：午火为文昌星，大运逢文昌学业运佳；午{ri_zhi}暗合引动夫妻宫，此运有情缘萌动；午火加强时干丁火食神的力量，才华创造力在此运中开始显现。')
        pdf.body_text(f'{cd["gz"]}大运整体评价：这是命主的黄金成长期。印星到位扶身，文昌到位助学，食神泄秀显才华。大学阶段在此运中度过，专业选择（电子信息）契合火印组合。唯一的隐忧是午火食神泄身——才华展示的同时也消耗精力，不可过度透支。')

    pdf.sub_title('5.3 未来大运简析')
    if len(du) >= 3:
        d3 = du[2]
        pdf.body_text(f'{d3["gz"]}运（{d3["start_year"]}-{d3["end_year"]}，{d3["start_age"]:.0f}-{d3["end_age"]:.0f}岁）：辛金七杀透干——原局藏而不透的七杀被大运引动。巳火伤官制辛金七杀——"伤官合杀"化压力为权柄。巳申合水若化水成功则印星增力。此运是事业起飞或压力陡增的分水岭。')
    if len(du) >= 4:
        d4 = du[3]
        pdf.body_text(f'{d4["gz"]}运（{d4["start_year"]}-{d4["end_year"]}，{d4["start_age"]:.0f}-{d4["end_age"]:.0f}岁）：庚金正官终于从天干透出——原局藏申中的官星被引动。官星透干，事业进入正轨。辰酉合金加强七杀，庚申通气官星得根。官杀力量聚合，压力不小。好在辰为水库，暗藏癸水偏印——官印相生的格局在此运显现。正官格真正发挥作用的十年。')
    if len(du) >= 5:
        d5 = du[4]
        pdf.body_text(f'{d5["gz"]}运及以后（{d5["start_age"]:.0f}岁后）：中年后运入木旺之地（卯、寅），日主得根，身弱得以扭转。中晚年运势优于早年。')

    # ===== 第六部分：2026流年 =====
    pdf.add_page()
    pdf.section_title('第六部分：2026丙午年流年分析')

    pdf.sub_title('6.1 流年干支：丙火伤官 + 午火食神')
    if current_dayun:
        pdf.body_text(f'2026年为丙午年。与大运{current_dayun["gz"]}形成双午并临 + 丙壬交冲的特殊组合。')

    pdf.sub_title('6.2 核心动态一：丙壬冲——伤官见印')
    pdf.body_text('流年天干丙火与大运天干壬水直接对冲。丙为伤官，壬为正印——伤官冲印。这是2026年最需关注的变动信号。《渊海子平》论伤官见印："伤官用印，印能制伤，最为上格。"但此处是伤官冲印而非印制伤——角色反了，是伤官主动冲击印星。印星代表学业、稳定性、依靠（老师/长辈/学校的庇护）。伤官代表自我主张、叛逆、改变现状的冲动。')
    pdf.body_text('具体含义：学业层面，大三阶段面临考研vs就业的选择，伤官冲印提示内心想要"打破现状"——可能对当前专业方向产生动摇。心态层面，自我主张增强，不再满足于按部就班。生活层面，印星受冲，生活环境可能有变动——换宿舍、实习离校、或考虑跨城市发展。')

    pdf.sub_title('6.3 核心动态二：双午——食神之力倍增')
    pdf.body_text('大运午 + 流年午，双午火食神。食神代表才华、创造力、表达欲。双午加强了电子信息专业（火=电子/信息）的敏感度，是技术能力提升的年份。但双午泄身——火旺木焚。日主乙木本就偏弱，双午盗泄木气，精力消耗大。需注意身体健康，不可过度熬夜或高负荷运转。')

    pdf.sub_title('6.4 核心动态三：丙辛合——伤官合杀')
    pdf.body_text('流年丙火与原局辛金七杀（在酉、丑中）相合。丙辛合化水——若化水成功，反而生木，转凶为吉。化神（水）在原局确实有根（亥水、申中壬水），合化有成功的基础。伤官合杀以才华和创造力驾驭压力和挑战——对在校学生而言，这意味着通过技术实力脱颖而出，把课程项目、竞赛、实习中的压力转化为展示能力的舞台。')

    pdf.sub_title(f'6.5 核心动态四：午{ri_zhi}暗合——夫妻宫引动')
    pdf.body_text(f'双午与日支{ri_zhi}水暗合。日支为夫妻宫，暗合为不明显的缘分信号。{current_age_2026}岁正值大学阶段，今年异性缘分有微妙变化——可能是同班同学、项目搭档、或实习场合认识的异性。但这个年龄的缘分通常是"练爱"而非婚姻，以平常心对待即可。')

    pdf.sub_title('6.6 2026年结论')
    pdf.body_text('吉：技术能力提升、创造力爆发、伤官合杀以才华应对挑战。')
    pdf.body_text('凶：伤官冲印学业稳定性有波动、双午泄身精力消耗大。')
    pdf.body_text('关键建议：在做学业/就业重大决定前多咨询师友（印星的现实对应），不要凭一时冲动（伤官）做决定。')

    # ===== 第七部分：事业财运 =====
    pdf.add_page()
    pdf.section_title('第七部分：事业财运专项分析')

    pdf.sub_title('7.1 适合的行业方向')
    pdf.body_text('主线一——电子信息/科技研发（火+水组合）：丁火食神主电子、信息、光电；亥水正印主知识体系和理论储备。技术型知识工作者的典型配置。细分方向：嵌入式系统、通信工程、芯片设计、软件开发均可。用神为水，在电子信息中偏"软件/算法/数据"方向（水主流动、数据）优于纯硬件方向。')
    pdf.body_text('主线二——教育/研究/学术（印星用神）：印星为第一用神，印主学术、教育、知识传递。如果继续深造读研读博，走科研或高校教师路线，是用神得位的选择。正官格+印星，天然适合需要资质/证书/职称体系的机构。')
    pdf.body_text('主线三——金融/数据分析（财+官组合）：偏财己土在时支丑中，财星入库。电子信息+金融的交叉领域（量化分析、金融科技）也可考虑。但原局土弱，非首选。')
    pdf.body_text('行业五行依据：第一用神为水（流动、智识、数据、网络），第二用神为木（教育、文化、成长性行业），才华出口为火（电子、能源、信息）。综合为水木火三行相生的科技教育领域。')

    pdf.sub_title('7.2 创业 vs 上班')
    cd_end = int(current_dayun['end_age']) if current_dayun else 24
    s3s = int(du[2]['start_age']) if len(du) >= 3 else 24
    s3e = int(du[2]['end_age']) if len(du) >= 3 else 34
    s4s = int(du[3]['start_age']) if len(du) >= 4 else 34
    s3gz = du[2]['gz'] if len(du) >= 3 else '辛巳'
    cdgz = current_dayun['gz'] if current_dayun else ''
    pdf.body_text('结论：适合上班，尤其适合"有技术话语权的上班"而非纯执行岗位。正官格天然适合规则框架内的组织。身弱财弱——财星均藏而不透且正财空亡，不适合一夜暴富型创业。食神在时柱，食神生财的路径是"先有技术再有变现"。比劫帮身，有合作精神，但劫财夺财需注意合伙人利益分配。')
    pdf.body_text(f'时间节奏：{cd_end}岁之前（{cdgz}运）踏实积累技术；{s3s}-{s3e}岁（{s3gz}运）从技术骨干向管理者过渡；{s4s}岁之后可考虑技术创业或独立执业。')

    pdf.sub_title('7.3 财运层次评估')
    pdf.body_text('类型：正财为主（戊土在申）、偏财为辅（己土在丑）。正财空亡——稳定工资收入的积累速度慢于常人，但会来，只是来得迟。层次：中等偏上。不是大富之命（财星不旺+空亡），但也不会穷困（印星贴身，总有后路）。财运是典型的"以技术换钱"模式——技术越精，收入越稳。')
    s3late = int(s3s + (s3e - s3s) * 0.7)
    s4gz = du[3]['gz'] if len(du) >= 4 else '庚辰'
    pdf.body_text(f'发财时机：{s3gz}运后期（约{s3late}岁前后）技术成熟开始变现；{s4gz}运（{s4s}-{s4s+10}岁）正官正财正印齐来，事业黄金期；财库（丑）开库之年需戌年冲开——2030庚戌年（{2030-birth_year}岁）、2042壬戌年（{2042-birth_year}岁）可能有意外之财或投资机会。')

    pdf.sub_title('7.4 具体建议')
    pdf.body_text('行业五行：水木优先，火次之。电子信息（火水）方向已选对，建议往数据/算法/网络（水属性更强）细分。')
    pdf.body_text('方位：北方（水）或东方（木）有利。珠三角已在南方（火偏旺），若未来考虑迁徙，长三角（东偏北）更适合。')
    pdf.body_text('合作模式：技术入股优于纯资金合伙。')
    pdf.body_text(f'时机：{cd_end}岁之前不要碰高风险投资。偏财在时柱，投资理财的能力在中年后才会成熟。')

    # ===== 第八部分：姻缘恋爱 =====
    pdf.add_page()
    pdf.section_title('第八部分：姻缘恋爱专项分析')

    pdf.sub_title('8.1 配偶核心特征')
    pdf.body_text(f'日支{ri_zhi}藏壬水正印——配偶性格温和、顾家、对自己有包容力。正印坐夫妻宫，配偶是"贤内助"型，在精神层面给自己很大支持。{ri_zhi}水为用神——配偶是自己命中的贵人，婚后运势会有提升。正财戊土在申中藏而不透且空亡——正缘来得晚，配偶行事风格偏低调、不张扬。')
    pdf.body_text('申亥相害需注意——夫妻宫被月令所害，夫妻关系中存在暗中的不协调。不是激烈争吵型（六冲才是），而是内在的、慢性的摩擦——比如生活习惯差异，或与父母（月令为父母宫）之间的隐性矛盾影响婚姻。')
    pdf.body_text(f'配偶职业倾向：日支{ri_zhi}水为用神，配偶职业可能涉及水木行业——教育、文化、医疗、心理咨询、媒体等。{ri_zhi}水正印配壬水，配偶学历不低、有知识底蕴。认识途径：日支{ri_zhi}为驿马——通过"动"中相识——同学/同事/朋友介绍/异地。')

    pdf.sub_title('8.2 正缘出现时间窗口')
    if current_dayun:
        pdf.body_text(f'大运窗口：{cdgz}运（{current_dayun["start_age"]:.0f}-{current_dayun["end_age"]:.0f}岁）午{ri_zhi}暗合引动夫妻宫，有恋爱机会，但多为"练习型"感情，校园恋情难修成正果。{s3gz}运（{s3s}-{s3e}岁）巳申合引动申中戊土正财——这是正缘最可能出现的十年。')
    pdf.body_text('最可能应期流年：')
    pdf.body_text(f'2028戊申年——正财戊土透干，申填实空亡。财星第一次透出天干且填实空亡，正缘信号极强。约{2028-birth_year}岁，应届毕业，是适龄婚恋起点。')
    pdf.body_text(f'2030庚戌年——庚金正官合身（乙庚合），戌冲丑（财库开），桃花与财星联动。约{2030-birth_year}岁。')
    pdf.body_text(f'2032壬子年——水旺印旺，稳定感增强。若之前已有稳定对象，此年是订婚/结婚的有利年份。')
    pdf.body_text(f'结论：恋爱不愁（{cdgz}运午{ri_zhi}暗合已有引动），但正缘/婚姻层面，2028戊申年是第一个高质量窗口期。在此之前，以积累自身为主。')

    pdf.sub_title('8.3 婚姻质量评估')
    pdf.body_text(f'利好因素：日支{ri_zhi}水为用神，配偶对己有助力，这是婚姻质量最核心的正面指标；正官格命主对婚姻有责任心；天乙贵人在亥不空，配偶自身有福气，也能旺到自己。')
    pdf.body_text('风险点：申亥相害——需婚后独立居住缓解；财星藏而不透+空亡——需走"先了解后发展"路线，不要追求一见钟情；时支丑藏偏财——中晚年异性缘仍存，需注意婚后边界感。')

    pdf.sub_title('8.4 2026年感情运势')
    pdf.body_text(f'双午暗合日支{ri_zhi}水夫妻宫——今年感情上不平静。但这个年龄（{current_age_2026}岁）的感情，多半是校园恋情，不必以婚姻标准去套。食神年谈恋爱容易"感觉来得快去得也快"。单身者顺其自然，如果遇到了先做朋友互相了解。已在恋爱中者，伤官透干脾气会比平时大，容易因小事起争执。')

    pdf.sub_title('8.5 择偶指引')
    pdf.body_text(f'五行：配偶八字宜水木旺（生扶你的用神），忌金土重（加重官杀克身）。日支：对方日支宜与{ri_zhi}相合——寅（寅{ri_zhi}合）、卯（卯{ri_zhi}半合木局）、未（{ri_zhi}未拱合）都是良配。忌巳（巳{ri_zhi}冲——夫妻宫正冲，最忌）。')

    # ===== 第九部分：性格与健康 =====
    pdf.add_page()
    pdf.section_title('第九部分：性格特征')

    pdf.sub_title('9.1 外柔内刚、规则感强')
    pdf.body_text('乙木日主（花草之木）天性温和柔韧，外在给人亲切好相处的印象。但月令正官格、乙庚暗合——内心有一套严格的行为准则和道德底线。《渊海子平》谓："正官者，以日为阳，克我为阴……正官为诸格之首。"正官人守规矩、重名誉、不越界。典型的"外表好说话，骨子里有杆秤"。优点：诚信可靠，做事有章法。缺点：有时候过于在意别人怎么看自己，给自己徒增压力。')

    pdf.sub_title('9.2 思虑深、心事重')
    pdf.body_text('官杀混杂+官杀空亡+申亥相害——三重因素叠加，导致内心世界远比外在表现要复杂。官杀混杂让人想得多（多个方向同时权衡），空亡让这些想法缺乏确定的落点，申亥害则制造了内在的不协调感。"心事重、容易想太多"的命理根源就在于此。优点：思考深入、有洞察力、不会冲动行事。缺点：容易陷入"想太多做太少"的循环。')

    pdf.sub_title('9.3 独立但重感情')
    pdf.body_text('日坐驿马+申亥相害（早年离家寄宿），养成了独立自主的能力。亥水正印贴身，内心渴望安全感、渴望被理解。比劫帮身（乙甲并透），对朋友讲义气、愿意合作。优点：独立不依赖、能扛事、对朋友真诚。缺点：独立久了，有时不知道如何向人求助。')

    pdf.section_title('第十部分：健康养生')

    pdf.sub_title('10.1 先天体质薄弱环节')
    pdf.body_text('金木交战——肝胆与呼吸系统：申月金旺克木，日主乙木偏弱。木主肝胆、神经系统、筋腱。金主肺、呼吸道、皮肤、大肠。金木相战，先天薄弱在肝脏（乙木）和呼吸系统（申金）之间。具体表现为：容易疲劳（肝主筋，木弱则耐力不足）、情绪波动影响消化（木克土）、季节交替时容易感冒/过敏。')
    pdf.body_text('火土晦暗——脾胃与精力：时干丁火食神坐丑土（湿土晦火），丁火被晦，容易有"思虑过度导致失眠/精力不济"的问题。心事重是身体症状的心理根源。')
    pdf.body_text('水局尚可——肾与泌尿系统：亥水正印不空，申中壬水也不空，水行不弱。肾脏、泌尿系统没有先天大碍。')

    pdf.sub_title('10.2 养生方向')
    pdf.body_text('养木：多接触自然，适当户外运动。菊花茶、枸杞养肝明目。不熬夜（子时前睡，养肝胆）。')
    pdf.body_text('疏土养火：脾胃是后天之本，规律饮食、避免暴饮暴食。适当运动出微汗（火主宣发），有助排解思虑。')
    pdf.body_text('水润木生：亥水为用神，可适当增加水性活动——游泳、泡澡、多喝水。亥水也是智慧之水，读书学习本身就是一种滋养。')

    # ===== 第十一部分：总结 =====
    pdf.add_page()
    pdf.section_title('第十一部分：一生走势总结')

    pdf.table_row(['阶段', '大运', '主题'], [35, 40, 95], header=True)
    themes_short = [
        '学业打底，虽非名校但根基尚可',
        '黄金成长期，技术积累 + 情窦初开',
        '事业起飞/压力陡增，伤官合杀化压力为权柄',
        '正官透干，事业进入正轨，财运稳步增长',
        '财坐比劫，中晚年运势优于早年',
        '日主得根，身弱扭转',
        '食伤生财，晚景安宁',
        '水旺扶身，吉祥',
    ]
    for i, d in enumerate(du):
        theme = themes_short[i] if i < len(themes_short) else ''
        pdf.table_row([f'{d["start_age"]:.0f}-{d["end_age"]:.0f}岁', d['gz'], theme], [35, 40, 95])

    pdf.ln(8)
    pdf.body_text(f'《滴天髓》有言："何知其人寿，性定元神厚。"你这局最大的优点是{ri_zhi}水正印贴身不空——印星是"元神"所在，它不空，你的根本就不会倒。官杀空亡给不了你显赫的权势，但给了你喘息的空间；食神虚浮给不了你横溢的才华，但给了你创造的火种。')
    pdf.ln(3)
    pdf.body_text(f'你{current_age_2026}岁，{cdgz}大运才走了一半，一切才刚开始。')

    pdf.ln(10)
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin + 30, pdf.get_y(), pdf.w - pdf.r_margin - 30, pdf.get_y())
    pdf.ln(8)
    pdf.set_font('Fang', '', 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 6, '免责声明：本报告仅为传统命理文化探讨，内容仅供参考，不作为人生决策依据。', align='C')
    pdf.ln(6)
    pdf.cell(0, 6, 'Generated by traditional-bazi-master Agent · 2026年5月27日', align='C')

    # ===== 保存 =====
    output_dir = r'C:\Users\A2260\Desktop\Destiny_agent\Archive'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '八字命理分析报告_20050819.pdf')
    pdf.output(output_path)
    print(f'PDF已生成: {output_path}')
    return output_path


def build_generic_pdf(plate, output_bytes: bool = True):
    """生成通用八字命盘 PDF 报告（纯数据，无断语）

    Args:
        plate: BaziPlate 对象（已调用 compute()）
        output_bytes: True 返回 bytes，False 保存到文件

    Returns:
        bytes 或文件路径
    """
    from datetime import date

    s = plate.sizhu
    qy = plate.qiyun
    du = plate.dayun
    kong = plate.kongwang

    ri_gan = s['day']['gan']
    ri_zhi = s['day']['zhi']
    yue_zhi = s['month']['zhi']
    shi_zhi = s['hour']['zhi']
    shi_idx = DI_ZHI.index(shi_zhi)
    shichen = SHICHEN.get(shi_idx, f'{shi_zhi}时')
    solar = plate.solar_adjusted
    lunar = plate.lunar

    birth_dt = plate.birth_dt
    birth_str = f'{birth_dt.year}年{birth_dt.month}月{birth_dt.day}日 {birth_dt.hour:02d}:{birth_dt.minute:02d}（{shichen}）'
    lunar_str = f'{plate.year_type[0]}历{lunar["year"]}年{lunar["month"]}月{lunar["day"]}日{shichen}'
    if lunar['is_leap']:
        lunar_str += '（闰月）'
    plate_date = date.today().strftime('%Y年%m月%d日')

    pdf = BaziPDF()

    # ===== 封面 =====
    pdf.cover_page(birth_str, plate.gender, plate.location, plate_date)

    # ===== 第一章：命盘总览 =====
    pdf.add_page()
    pdf.section_title('第一章：命盘总览')

    pdf.sub_title('1.1 基本信息')
    pdf.body_text(f'公历：{birth_str}')
    pdf.body_text(f'农历：{lunar_str}')
    pdf.body_text(f'性别：{plate.gender}    出生地：{plate.location}    经度：约{plate.longitude}°E')
    pdf.body_text(f'真太阳时校正：约{solar["adjusted_hour"]:.1f}时（校正{solar["correction_minutes"]:.0f}分钟）')
    pdf.body_text(f'年柱阴阳：{plate.year_type}')
    pdf.body_text(f'日主：{ri_gan}（{ri_zhi}）')

    pdf.ln(3)
    pdf.sub_title('1.2 四柱干支')
    ss = plate.shishen
    pdf.table_row(['', '年柱', '月柱', '日柱', '时柱'], [24, 36, 36, 36, 36], header=True)
    pdf.table_row(['天干', f'{s["year"]["gan"]}（{ss["year"]}）',
                         f'{s["month"]["gan"]}（{ss["month"]}）',
                         f'{s["day"]["gan"]}（日主）',
                         f'{s["hour"]["gan"]}（{ss["hour"]}）'],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['地支', s['year']['zhi'], s['month']['zhi'],
                         s['day']['zhi'], s['hour']['zhi']],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['纳音', plate.nayin['year'], plate.nayin['month'],
                         plate.nayin['day'], plate.nayin['hour']],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['藏干', _canggan_str(s['year']['zhi']), _canggan_str(s['month']['zhi']),
                         _canggan_str(s['day']['zhi']), _canggan_str(s['hour']['zhi'])],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['十二长生', plate.changsheng['year'], plate.changsheng['month'],
                            plate.changsheng['day'], plate.changsheng['hour']],
                  [24, 36, 36, 36, 36])

    pdf.ln(3)
    pdf.sub_title('1.3 核心数据')
    # 空亡
    kong_pillars = [p for p in ['year', 'month', 'day', 'hour'] if kong['pillars'][p]]
    kong_desc = '、'.join([f'{p}柱({s[p]["zhi"]})' for p in kong_pillars]) if kong_pillars else '无'
    pdf.body_text(f'日柱旬空：{ri_gan}{ri_zhi}日属{kong["kong1"]}{kong["kong2"]}旬，空亡 {kong["kong1"]} {kong["kong2"]}')
    pdf.body_text(f'空亡落柱：{kong_desc}')
    pdf.body_text(f'胎元：{plate.taiyuan}    命宫：{plate.minggong}    身宫：{plate.shengong}')

    # 六亲十神
    pdf.ln(3)
    pdf.sub_title('1.4 十神分布')
    shishen_items = []
    for p in ['year', 'month', 'day', 'hour']:
        shishen_items.append(f'{p}柱：{ss[p]}')
    pdf.body_text('  |  '.join(shishen_items))
    pdf.body_text('十神以日干为中心，反映六亲关系和社会角色。比肩劫财为同辈助力，食神伤官为才华输出，正财偏财为财富获取，正官七杀为事业压力，正印偏印为学识靠山。')

    # ===== 第二章：起运与大运 =====
    pdf.add_page()
    pdf.section_title('第二章：起运与大运')

    pdf.sub_title('2.1 起运计算')
    pdf.body_text(f'起运年龄：{qy["qiyun_age"]:.2f} 岁（虚岁 {qy["qiyun_age_xu"]} 岁）')
    pdf.body_text(f'交运年份：约 {qy["qiyun_year"]:.0f} 年')
    pdf.body_text(f'大运方向：{qy["direction"]}')
    pdf.body_text(f'距节气日数：{qy["diff_days"]} 天')
    pdf.body_text(f'计算原理：出生时刻至相邻节气（{"下一" if qy["forward"] else "上一"}个）的日数除以3，3天折合1岁起运。《渊海子平》云："三日为一岁，一日为四月，一时为十日。"')

    pdf.ln(3)
    pdf.sub_title('2.2 大运排盘')
    pdf.table_row(['步数', '大运干支', '起运年龄', '结束年龄', '起运年份', '结束年份'],
                  [18, 40, 30, 30, 36, 36], header=True)
    for d in du:
        pdf.table_row([
            f'第{d["step"]}步',
            d['gz'],
            f'{d["start_age"]:.1f}岁',
            f'{d["end_age"]:.1f}岁',
            f'{d["start_year"]}年',
            f'{d["end_year"]}年',
        ], [18, 40, 30, 30, 36, 36])

    pdf.body_text('大运以月柱为起点，阳年男/阴年女顺排，阳年女/阴年男逆排，每步大运管十年。大运天干主前五年，地支主后五年。')

    # ===== 第三章：神煞 =====
    pdf.add_page()
    pdf.section_title('第三章：神煞速览')

    # 天乙贵人
    pdf.sub_title('3.1 天乙贵人')
    gan = ri_gan
    guiren = {'甲': '丑未', '乙': '子申', '丙': '亥酉', '丁': '亥酉', '戊': '丑未',
              '己': '子申', '庚': '丑未', '辛': '午寅', '壬': '巳卯', '癸': '巳卯'}
    gr = guiren.get(gan, '')
    pdf.body_text(f'日干{gan}天乙贵人：{gr}')
    # 检查贵人是否在原局
    gr_dz = [gr[0], gr[1]] if len(gr) == 2 else []
    gr_in_plate = []
    for p in ['year', 'month', 'day', 'hour']:
        if s[p]['zhi'] in gr_dz:
            gr_in_plate.append(f'{p}柱{s[p]["zhi"]}')
    if gr_in_plate:
        pdf.body_text(f'贵人入局：{"、".join(gr_in_plate)}')
    else:
        pdf.body_text('贵人未入原局，待大运流年引动。')

    # 驿马
    pdf.sub_title('3.2 驿马')
    # 驿马：申子辰在寅，寅午戌在申，巳酉丑在亥，亥卯未在巳
    yima_map = {'申': '寅', '子': '寅', '辰': '寅',
                '寅': '申', '午': '申', '戌': '申',
                '巳': '亥', '酉': '亥', '丑': '亥',
                '亥': '巳', '卯': '巳', '未': '巳'}
    yima_dz = yima_map.get(ri_zhi, '')
    pdf.body_text(f'日支{ri_zhi}驿马在{yima_dz}')
    for p in ['year', 'month', 'day', 'hour']:
        if s[p]['zhi'] == yima_dz:
            pdf.body_text(f'驿马入{p}柱——一生多动，变动中求发展。')

    # 桃花
    pdf.sub_title('3.3 桃花')
    taohua_map = {'申': '酉', '子': '酉', '辰': '酉',
                  '寅': '卯', '午': '卯', '戌': '卯',
                  '巳': '午', '酉': '午', '丑': '午',
                  '亥': '子', '卯': '子', '未': '子'}
    taohua_dz = taohua_map.get(ri_zhi, '')
    pdf.body_text(f'日支{ri_zhi}桃花在{taohua_dz}')
    for p in ['year', 'month', 'day', 'hour']:
        if s[p]['zhi'] == taohua_dz:
            pdf.body_text(f'桃花入{p}柱。')

    # 华盖
    pdf.sub_title('3.4 华盖')
    huagai_map = {'申': '辰', '子': '辰', '辰': '辰',
                  '寅': '戌', '午': '戌', '戌': '戌',
                  '巳': '丑', '酉': '丑', '丑': '丑',
                  '亥': '未', '卯': '未', '未': '未'}
    huagai_dz = huagai_map.get(ri_zhi, '')
    pdf.body_text(f'日支{ri_zhi}华盖在{huagai_dz}')
    for p in ['year', 'month', 'day', 'hour']:
        if s[p]['zhi'] == huagai_dz:
            pdf.body_text(f'华盖入{p}柱——有精神追求、玄学缘分或艺术天赋。')

    # 文昌
    pdf.sub_title('3.5 文昌贵人')
    wenchang_map = {'甲': '巳', '乙': '午', '丙': '申', '丁': '酉', '戊': '申',
                    '己': '酉', '庚': '亥', '辛': '子', '壬': '寅', '癸': '卯'}
    wc = wenchang_map.get(gan, '')
    pdf.body_text(f'日干{gan}文昌在{wc}')
    for p in ['year', 'month', 'day', 'hour']:
        if s[p]['zhi'] == wc:
            pdf.body_text(f'文昌入{p}柱——利学业、考试、文书。')

    # ===== 第四章：地支关系 =====
    pdf.add_page()
    pdf.section_title('第四章：地支关系')

    pdf.sub_title('4.1 藏干详情')
    for p in ['year', 'month', 'day', 'hour']:
        items = plate.canggan[p]
        gan_str = ' · '.join(f'{g}({r:.0%})' for g, r in items) if items else '无'
        pdf.body_text(f'{p}支 {s[p]["zhi"]}：{gan_str}')

    pdf.sub_title('4.2 十二长生详解')
    for p in ['year', 'month', 'day', 'hour']:
        gz = s[p]['gz']
        cs = plate.changsheng[p]
        pdf.body_text(f'{p}柱 {gz}：{cs}')

    pdf.body_text('十二长生顺序：长生 → 沐浴 → 冠带 → 临官 → 帝旺 → 衰 → 病 → 死 → 墓 → 绝 → 胎 → 养')
    pdf.body_text(f'日主{ri_gan}为{plate.year_type[0]}干，在十二地支上的状态反映了日主在不同宫位的能量强弱。临官、帝旺为强位；衰、病、死、墓、绝为弱位。')

    pdf.ln(3)
    pdf.sub_title('4.3 纳音五行')
    for p in ['year', 'month', 'day', 'hour']:
        pdf.body_text(f'{p}柱 {s[p]["gz"]}：{plate.nayin[p]}')

    # ===== 免责声明 =====
    pdf.ln(15)
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin + 30, pdf.get_y(), pdf.w - pdf.r_margin - 30, pdf.get_y())
    pdf.ln(8)
    pdf.set_font('Fang', '', 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 6, '免责声明：本报告仅输出传统命理排盘数据，不含主观断语，仅供参考。', align='C')
    pdf.ln(6)
    pdf.cell(0, 6, f'Generated by BaziPaipan · {plate_date}', align='C')

    # ===== 输出 =====
    if output_bytes:
        return pdf.output()
    else:
        output_dir = r'C:\Users\A2260\Desktop\Destiny_agent\Archive'
        os.makedirs(output_dir, exist_ok=True)
        filename = f'八字命盘_{birth_dt.year}{birth_dt.month:02d}{birth_dt.day:02d}_{birth_dt.hour:02d}{birth_dt.minute:02d}.pdf'
        output_path = os.path.join(output_dir, filename)
        pdf.output(output_path)
        print(f'PDF已生成: {output_path}')
        return output_path


def build_analysis_pdf(plate, analysis_text: str, output_bytes: bool = True):
    """生成含 Agent 分析的完整 PDF 报告

    Args:
        plate: BaziPlate 对象
        analysis_text: Agent 分析文本（Markdown 格式）
        output_bytes: True 返回 bytes

    Returns:
        bytes 或文件路径
    """
    from datetime import date

    # 先生成数据部分
    data_pdf_bytes = build_generic_pdf(plate, output_bytes=True)

    # 创建新 PDF，先写数据部分，再附加分析
    pdf = BaziPDF()

    # ===== 封面 =====
    s = plate.sizhu
    shi_idx = DI_ZHI.index(s['hour']['zhi'])
    shichen = SHICHEN.get(shi_idx, f'{s["hour"]["zhi"]}时')
    birth_dt = plate.birth_dt
    birth_str = f'{birth_dt.year}年{birth_dt.month}月{birth_dt.day}日 {birth_dt.hour:02d}:{birth_dt.minute:02d}（{shichen}）'
    plate_date = date.today().strftime('%Y年%m月%d日')

    pdf.cover_page(birth_str, plate.gender, plate.location, plate_date)

    # ===== 数据部分：复用 build_generic_pdf 但保存到临时文件再拼接 =====
    # 简化做法：直接从 plate 生成关键表格

    # --- 命盘总览 ---
    pdf.add_page()
    pdf.section_title('第一章：命盘总览')

    pdf.sub_title('1.1 基本信息')
    solar = plate.solar_adjusted
    lunar = plate.lunar
    lunar_str = f'{plate.year_type[0]}历{lunar["year"]}年{lunar["month"]}月{lunar["day"]}日{shichen}'
    if lunar.get('is_leap'):
        lunar_str += '（闰月）'

    pdf.body_text(f'公历：{birth_str}')
    pdf.body_text(f'农历：{lunar_str}')
    pdf.body_text(f'性别：{plate.gender}    出生地：{plate.location}    经度：约{plate.longitude}°E')
    pdf.body_text(f'真太阳时校正：约{solar["adjusted_hour"]:.1f}时（校正{solar["correction_minutes"]:.0f}分钟）')
    pdf.body_text(f'日主：{s["day"]["gan"]}（{s["day"]["zhi"]}）  |  {plate.year_type}')

    pdf.ln(3)
    pdf.sub_title('1.2 四柱干支')
    ss = plate.shishen
    pdf.table_row(['', '年柱', '月柱', '日柱', '时柱'], [24, 36, 36, 36, 36], header=True)
    pdf.table_row(['天干', f'{s["year"]["gan"]}（{ss["year"]}）',
                         f'{s["month"]["gan"]}（{ss["month"]}）',
                         f'{s["day"]["gan"]}（日主）',
                         f'{s["hour"]["gan"]}（{ss["hour"]}）'],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['地支', s['year']['zhi'], s['month']['zhi'],
                         s['day']['zhi'], s['hour']['zhi']],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['纳音', plate.nayin['year'], plate.nayin['month'],
                         plate.nayin['day'], plate.nayin['hour']],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['藏干', _canggan_str(s['year']['zhi']), _canggan_str(s['month']['zhi']),
                         _canggan_str(s['day']['zhi']), _canggan_str(s['hour']['zhi'])],
                  [24, 36, 36, 36, 36])
    pdf.table_row(['十二长生', plate.changsheng['year'], plate.changsheng['month'],
                            plate.changsheng['day'], plate.changsheng['hour']],
                  [24, 36, 36, 36, 36])

    pdf.ln(3)
    pdf.sub_title('1.3 核心数据')
    kong = plate.kongwang
    pdf.body_text(f'日柱旬空：{kong["kong1"]}{kong["kong2"]}')
    pdf.body_text(f'胎元：{plate.taiyuan}    命宫：{plate.minggong}    身宫：{plate.shengong}')
    qy = plate.qiyun
    pdf.body_text(f'起运：{qy["qiyun_age"]:.2f} 岁（{qy["direction"]}，约{qy["qiyun_year"]:.0f}年交运）')

    # --- 大运 ---
    pdf.add_page()
    pdf.section_title('第二章：大运')
    du = plate.dayun
    pdf.table_row(['步数', '大运干支', '年龄', '年份'], [22, 36, 44, 58], header=True)
    for d in du:
        pdf.table_row([
            f'第{d["step"]}步',
            d['gz'],
            f'{d["start_age"]:.0f}-{d["end_age"]:.0f}岁',
            f'{d["start_year"]}-{d["end_year"]}年',
        ], [22, 36, 44, 58])

    # ===== Agent 分析部分 =====
    pdf.add_page()
    pdf.section_title('第三章：Agent 深度分析')

    # 将 Markdown 分析文本分段写入
    paragraphs = analysis_text.split('\n\n')
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # 标题行
        if para.startswith('### '):
            pdf.sub_title(para[4:].strip())
        elif para.startswith('## '):
            pdf.section_title(para[3:].strip())
        elif para.startswith('# '):
            pdf.section_title(para[2:].strip())
        elif para.startswith('- '):
            # 列表项
            for line in para.split('\n'):
                line = line.strip()
                if line.startswith('- '):
                    pdf.body_text('  • ' + line[2:])
                elif line:
                    pdf.body_text(line)
        elif '|' in para and para.count('\n') >= 1:
            # 简单表格处理
            lines = para.split('\n')
            if len(lines) >= 2:
                # 检查是否确实是表格（第二行含 ---）
                if '---' in lines[1] if len(lines) > 1 else False:
                    try:
                        header_cells = [c.strip() for c in lines[0].split('|') if c.strip()]
                        if header_cells:
                            ncols = len(header_cells)
                            col_w = (pdf.w - pdf.l_margin - pdf.r_margin) // ncols
                            widths = [col_w] * ncols
                            pdf.table_row(header_cells, widths, header=True)
                            for row in lines[2:]:
                                cells = [c.strip() for c in row.split('|') if c.strip()]
                                if cells:
                                    pdf.table_row(cells, widths)
                        continue
                    except Exception:
                        pass
            pdf.body_text(para)
        else:
            pdf.body_text(para)

    # ===== 免责声明 =====
    pdf.ln(15)
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin + 30, pdf.get_y(), pdf.w - pdf.r_margin - 30, pdf.get_y())
    pdf.ln(8)
    pdf.set_font('Fang', '', 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 6, '免责声明：本报告中的分析内容由 AI 生成，仅代表传统命理文化探讨，不作为人生决策依据。', align='C')
    pdf.ln(6)
    pdf.cell(0, 6, f'Generated by BaziPaipan + traditional-bazi-master Agent · {plate_date}', align='C')

    # ===== 输出 =====
    if output_bytes:
        return pdf.output()
    else:
        output_dir = r'C:\Users\A2260\Desktop\Destiny_agent\Archive'
        os.makedirs(output_dir, exist_ok=True)
        filename = f'八字分析报告_{birth_dt.year}{birth_dt.month:02d}{birth_dt.day:02d}_{birth_dt.hour:02d}{birth_dt.minute:02d}.pdf'
        output_path = os.path.join(output_dir, filename)
        pdf.output(output_path)
        print(f'PDF已生成: {output_path}')
        return output_path


if __name__ == '__main__':
    build_pdf()
