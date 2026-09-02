import os
import re
import socket
import json
import time
import requests

# 标准 IPv4 正则表达式
IP_REGEX = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

# 过滤常见的 DNS 服务器或内网 IP
FILTER_IPS = {
    '1.1.1.1', '1.0.0.1', '8.8.8.8', '8.8.4.4', '114.114.114.114',
    '127.0.0.1', '0.0.0.0', '255.255.255.255'
}

# Cloudflare 机场三字码（Colo）与国家/地区中文映射表
COLO_TO_COUNTRY = {
    "NRT": "日本", "KIX": "日本", "NGO": "日本", "FUK": "日本",
    "SIN": "新加坡",
    "HKG": "香港",
    "TPE": "台湾", "KHH": "台湾",
    "ICN": "韩国", "GMP": "韩国",
    "SJC": "美国", "LAX": "美国", "SFO": "美国", "IAD": "美国", "ORD": "美国",
    "EWR": "美国", "ATL": "美国", "MIA": "美国", "DFW": "美国", "SEA": "美国",
    "LHR": "欧洲", "CDG": "欧洲", "FRA": "欧洲", "AMS": "欧洲", "MAD": "欧洲"
}

# 标准国家代码与中文映射
COUNTRY_CODE_MAP = {
    "JP": "日本",
    "SG": "新加坡",
    "HK": "香港",
    "TW": "台湾",
    "KR": "韩国",
    "US": "美国",
    "GB": "欧洲",
    "FR": "欧洲",
    "DE": "欧洲",
    "NL": "欧洲",
    "ES": "欧洲"
}

def is_valid_ipv4(ip):
    """验证是否为合法 IPv4 地址且不在过滤列表中"""
    if ip in FILTER_IPS:
        return False
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False

def resolve_dns(domain):
    """解析域名获取 A 记录"""
    ips = []
    try:
        addr_info = socket.getaddrinfo(domain, 80, socket.AF_INET)
        for item in addr_info:
            ip = item[4][0]
            if is_valid_ipv4(ip):
                ips.append(ip)
    except Exception as e:
        print(f"解析域名 {domain} 失败: {e}")
    return list(set(ips))

def fetch_ips_generic(url):
    """通用抓取方法：支持自动识别 JSON 与文本中的 IP"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    ips = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            # 优先尝试作为 JSON 解析并递归提取所有符合格式的 IP
            try:
                data = response.json()
                def extract_from_json(obj):
                    if isinstance(obj, str) and is_valid_ipv4(obj):
                        ips.append(obj)
                    elif isinstance(obj, dict):
                        for v in obj.values():
                            extract_from_json(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            extract_from_json(v)
                extract_from_json(data)
                if ips:
                    return list(set(ips))
            except Exception:
                pass
            
            # 若不是 JSON，使用正则匹配提取
            text = response.text
            found = re.findall(IP_REGEX, text)
            valid = [ip for ip in found if is_valid_ipv4(ip)]
            return list(set(valid))
    except Exception as e:
        print(f"请求 {url} 失败: {e}")
    return []

def fetch_345673_ips():
    """专门解析 345673.xyz 的 POST API 接口以提取 IP"""
    url = "https://api.345673.xyz/get_data"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Content-Type': 'application/json'
    }
    payload = {"key": "o1zrmHAF"}  # 公开公益 Key
    ips = []
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200 or data.get("status"):
                info = data.get("info", {})
                def extract_ips(obj):
                    if isinstance(obj, str) and is_valid_ipv4(obj):
                        ips.append(obj)
                    elif isinstance(obj, dict):
                        for v in obj.values():
                            extract_ips(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            extract_ips(v)
                extract_ips(info)
    except Exception as e:
        print(f"请求 345673.xyz 失败: {e}")
    return list(set(ips))

# ==================== 智能地理位置匹配引擎 ====================

def fetch_wetest_mapping():
    """通过 WeTest 的官方 API 建立精确的 IP -> Colo -> 地区映射"""
    url = "https://www.wetest.vip/api/cf2dns/get_cloudflare_ip?key=o1zrmHAF&type=v4"
    headers = {'User-Agent': 'Mozilla/5.0'}
    ip_to_country = {}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") and "info" in data:
                for item in data["info"]:
                    ip = item.get("ip")
                    colo = str(item.get("colo", "")).upper()
                    if ip and is_valid_ipv4(ip):
                        country = COLO_TO_COUNTRY.get(colo, "其他")
                        if country != "其他":
                            ip_to_country[ip] = country
    except Exception as e:
        print(f"获取 WeTest 路由映射失败: {e}")
    return ip_to_country

def fetch_030101_mapping():
    """通过社区优选 IP 数据库提取 IP -> 地区的中文映射关系"""
    url = "https://ipdb.api.030101.xyz/?type=bestcf&country=true"
    headers = {'User-Agent': 'Mozilla/5.0'}
    ip_to_country = {}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            for line in response.text.splitlines():
                found_ips = re.findall(IP_REGEX, line)
                if found_ips:
                    ip = found_ips[0]
                    country = "其他"
                    if "日本" in line or "JP" in line or "Japan" in line:
                        country = "日本"
                    elif "新加坡" in line or "SG" in line or "Singapore" in line:
                        country = "新加坡"
                    elif "香港" in line or "HK" in line or "Hong Kong" in line:
                        country = "香港"
                    elif "台湾" in line or "TW" in line or "Taiwan" in line:
                        country = "台湾"
                    elif "韩国" in line or "KR" in line or "Korea" in line:
                        country = "韩国"
                    elif "美国" in line or "US" in line or "United States" in line:
                        country = "美国"
                    elif "欧洲" in line or "EU" in line:
                        country = "欧洲"
                    
                    if country != "其他":
                        ip_to_country[ip] = country
    except Exception as e:
        print(f"获取 030101 数据库映射失败: {e}")
    return ip_to_country

def fetch_geoip_batch(ips):
    """通过 ip-api 批量定位接口，对剩余未成功定位的 IP 进行兜底查询"""
    ip_to_country = {}
    if not ips:
        return ip_to_country
    
    url = "http://ip-api.com/batch?fields=query,countryCode"
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }
    
    chunk_size = 100
    for i in range(0, len(ips), chunk_size):
        chunk = ips[i:i + chunk_size]
        payload = [{"query": ip} for ip in chunk]
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                results = response.json()
                for item in results:
                    ip = item.get("query")
                    code = str(item.get("countryCode", "")).upper()
                    if ip and code:
                        ip_to_country[ip] = COUNTRY_CODE_MAP.get(code, "其他")
            time.sleep(1) # 遵守 API 频率限制
        except Exception as e:
            print(f"GeoIP 批量兜底查询失败: {e}")
            
    return ip_to_country

# ==================== 主逻辑 ====================

def main():
    print("【开始爬取优选 IP 列表】")
    
    all_ips = set()
    results_by_source = {}
    
    # 1. 常规爬取源 (原有源 + 新增聚合及 GitHub 高频机器人源)
    sources = {
        # --- 原始源 ---
        "麒麟域名检测": "https://api.uouin.com/cloudflare.html",
        "WeTest.vip": "https://www.wetest.vip/page/cloudflare/address_v4.html",
        "hostmonit": "https://stock.hostmonit.com/CloudFlareYes",
        "115155": "https://monitor.115155.xyz/",
        "ip164746": "https://ip.164746.xyz/",
        "vps789": "https://vps789.com/vps/sum/cfIpTop20",
        "vvhan": "https://cf.vvhan.com/",
        
        # --- 新增 BestCF 聚合系列 (每半小时更新) ---
        "BestCF_WeTest": "https://bestcf.pages.dev/wetest/ipv4.txt",
        "BestCF_UOUIN": "https://bestcf.pages.dev/uouin/all.txt",
        "BestCF_Mia": "https://bestcf.pages.dev/xinyitang3/ipv4.txt",
        "BestCF_LuoLi": "https://bestcf.pages.dev/luoli/all.txt",
        "BestCF_CFYes": "https://bestcf.pages.dev/cfyes/ipv4.txt",
        
        # --- 新增 GitHub 优选测速机器人 Raw 列表 ---
        "GitHub_IPDB_ymyuuu": "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv4.txt",
        "GitHub_yuanxiawan": "https://raw.githubusercontent.com/yuanxiawan/cfipv4db/refs/heads/main/cfip.txt",
        "GitHub_love-ztm": "https://raw.githubusercontent.com/love-ztm/cfip/refs/heads/main/best_ips.txt"
    }
    
    for name, url in sources.items():
        print(f"正在抓取: {name} ...")
        ips = fetch_ips_generic(url)
        results_by_source[name] = ips
        all_ips.update(ips)
        print(f"从 {name} 获取到 {len(ips)} 个 IP")
        
    # 2. 特殊 POST API 源爬取
    print("正在请求 345673.xyz API 接口...")
    api_345673_ips = fetch_345673_ips()
    all_ips.update(api_345673_ips)
    results_by_source["345673_api"] = api_345673_ips
    print(f"从 345673.xyz 获取到 {len(api_345673_ips)} 个 IP")
        
    # 3. 解析 090227 优选域名获取 IP
    print("正在解析 090227 DNS 记录...")
    dns_domains = ["ct.090227.xyz", "cmcc.090227.xyz", "cf.090227.xyz"]
    dns_ips = []
    for domain in dns_domains:
        ips = resolve_dns(domain)
        dns_ips.extend(ips)
        all_ips.update(ips)
    results_by_source["090227_dns"] = list(set(dns_ips))
    print(f"DNS 解析完成，共获取 {len(set(dns_ips))} 个 IP")
    
    # 4. 运行地理位置分类引擎
    print("\n【启动地理位置分类引擎】")
    unique_ips = list(all_ips)
    classified_ips = {}  # 结构: { "日本": set(), "美国": set(), ... }
    
    # 获取高精度的映射源
    print("正在拉取 WeTest 和 030101 映射表...")
    wetest_map = fetch_wetest_mapping()
    db_030101_map = fetch_030101_mapping()
    
    # 本地合并映射
    ip_to_country_map = {}
    ip_to_country_map.update(db_030101_map)
    ip_to_country_map.update(wetest_map)
    
    # 筛选未匹配成功的 IP
    unmatched_ips = [ip for ip in unique_ips if ip not in ip_to_country_map]
    
    # 批量 GeoIP 自动定位
    if unmatched_ips:
        print(f"有 {len(unmatched_ips)} 个 IP 未在本地库中找到，正在启动批量在线 GeoIP 定位...")
        geoip_map = fetch_geoip_batch(unmatched_ips)
        ip_to_country_map.update(geoip_map)
        
    # 分类归入
    for ip in unique_ips:
        country = ip_to_country_map.get(ip, "其他")
        if country not in classified_ips:
            classified_ips[country] = set()
        classified_ips[country].add(ip)
        
    # 5. 保存文件到本地
    os.makedirs("output", exist_ok=True)
    
    # 保存全量去重后的 IP 列表
    sorted_all_ips = sorted(unique_ips)
    with open("output/ip_all.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_all_ips))
        
    # 按归属地分类保存
    for country, ip_set in classified_ips.items():
        sorted_ips = sorted(list(ip_set))
        filename = f"output/ip_{country}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted_ips))
        print(f"位置分类：{country} 包含 {len(sorted_ips)} 个优选 IP -> 保存至 {filename}")
        
    # 汇总 JSON 统计
    summary = {
        "total_count": len(sorted_all_ips),
        "by_country": {c: len(ips) for c, ips in classified_ips.items()},
        "by_source": results_by_source
    }
    with open("output/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    print(f"\n抓取与地理位置分类已全部完成！共收集并定位 {len(sorted_all_ips)} 个 IP。")

if __name__ == "__main__":
    main()
