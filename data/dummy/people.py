# -*- coding: utf-8 -*-
# 가상 조직도. 모든 인물·연락처는 가상이며 도메인은 .example(실제 주소와 겹치지 않음)
ADDR = "[본사 주소], LG CNS"  # 실제 주소 확인 전 자리표시자

def I(name, en, pos, org, eid, tel):  # 사내
    return dict(name=name, name_en=en, position=pos, team=org[-1], org=list(org),
                email=f"{eid}@lgcns.example", phone=tel, external=False)

def X(name, pos, company, dept, email, tel):  # 외부
    return dict(name=name, position=pos, team=dept, company=company,
                email=email, phone=tel, external=True)

CB, CD, FG, T1 = "클라우드사업부", "클라우드전환담당", "금융클라우드사업단", "클라우드전환1팀"
MG = "경영지원부문"
P = {
    "me":  I("이준호", "Junho Lee", "팀장", (CB, CD, FG, T1), "junho.lee", "02-0000-1101"),
    "jts": I("정태성", "Taesung Jung", "담당", (CB, CD), "taesung.jung", "02-0000-1001"),
    "hsw": I("한상우", "Sangwoo Han", "사업단장", (CB, CD, FG), "sangwoo.han", "02-0000-1010"),
    "kms": I("김민석", "Minseok Kim", "팀장", (CB, CD, FG, "클라우드전환2팀"), "minseok.kim", "02-0000-1201"),
    "pjy": I("박지영", "Jiyoung Park", "팀장", (CB, "사업관리담당", "사업기획팀"), "jiyoung.park", "02-0000-1501"),
    "ose": I("오세훈", "Sehun Oh", "팀장", (CB, CD, "기술지원사업단", "아키텍처팀"), "sehun.oh", "02-0000-1601"),
    "psh": I("임소희", "Sohee Lim", "책임", (CB, CD, FG, "사업단PMO"), "sohee.lim", "02-0000-1011"),
    "cyj": I("최유진", "Yujin Choi", "선임", (CB, CD, FG, T1), "yujin.choi", "02-0000-1102"),
    "kdy": I("강도윤", "Doyun Kang", "책임", (CB, CD, FG, T1), "doyun.kang", "02-0000-1103"),
    "ysy": I("윤서연", "Seoyeon Yoon", "선임", (CB, CD, FG, T1), "seoyeon.yoon", "02-0000-1104"),
    "ijh": I("임재현", "Jaehyun Lim", "사원", (CB, CD, FG, T1), "jaehyun.lim", "02-0000-1105"),
    "she": I("송하은", "Haeun Song", "책임", (CB, CD, FG, T1), "haeun.song", "02-0000-1106"),
    "mgy": I("문가영", "Gayoung Moon", "책임", (CB, "사업관리담당", "품질관리팀"), "gayoung.moon", "02-0000-1502"),
    "bsm": I("배수민", "Sumin Bae", "책임", (MG, "정보보호담당", "정보보안팀"), "sumin.bae", "02-0000-2101"),
    "jeb": I("조은비", "Eunbi Jo", "선임", (MG, "인사담당", "인사팀"), "eunbi.jo", "02-0000-2201"),
    "nhw": I("노현우", "Hyunwoo Noh", "책임", (MG, "구매담당", "구매팀"), "hyunwoo.noh", "02-0000-2301"),
    "sjh": I("서지훈", "Jihoon Seo", "선임", (MG, "재무담당", "재무팀"), "jihoon.seo", "02-0000-2401"),
    "his": I("황인성", "Insung Hwang", "책임", (MG, "IT운영담당", "IT운영팀"), "insung.hwang", "02-0000-2501"),
    "com": I("이소라", "Sora Lee", "선임", (MG, "커뮤니케이션담당", "사내커뮤니케이션팀"), "sora.lee", "02-0000-2601"),
    "nws": I("CNS 뉴스", "", "", (MG, "커뮤니케이션담당", "사내커뮤니케이션팀"), "cns-news", "02-0000-2600"),
    "jmh": X("장민호", "차장", "한빛은행", "IT기획부", "minho.jang@hanbitbank.example", "02-0000-7001"),
    "knr": X("권나래", "대리", "한빛은행", "IT기획부", "narae.kwon@hanbitbank.example", "02-0000-7002"),
    "bsh": X("백승현", "과장", "누리물류", "정보전략팀", "seunghyun.baek@nurilogis.example", "02-0000-8001"),
    "ykm": X("유경민", "매니저", "스카이넷클라우드", "파트너영업팀", "kyungmin.yoo@skynetcloud.example", "02-0000-9001"),
    "sem": X("테크포럼 사무국", "", "테크포럼", "사무국", "info@techforum.example", "02-0000-9101"),
}
DL = {"all": "all@lgcns.example", "lead": "cloud-leaders@lgcns.example", "t1": "cloud1@lgcns.example"}
OWNER = "me"
SUPERIORS = ["jts", "hsw"]
FAVORITES = ["jts", "hsw", "jmh", "kms", "cyj"]  # Outlook 즐겨찾기 = is_vip
