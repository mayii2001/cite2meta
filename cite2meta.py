import time
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
import urllib.request as libreq
import xml.etree.ElementTree as ET
from urllib.parse import quote
from tqdm import tqdm

# 提取DOI号的正则表达式
doi_pattern = re.compile(r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b', re.IGNORECASE)
# 提取arXiv号的正则表达式
arxiv_pattern = re.compile(r'arxiv.*?(\d{4}\.\d{1,5})', re.IGNORECASE)
# 提取URL的正则表达式
url_pattern = re.compile(r'https?://[^\s]+')

def extract_title(text):
    """
    提取引用文本中的标题。
    去除序号，并提取引文的第二部分作为标题。
    """

    # 去除开头的序号（如 "1.", "23." 等）
    text = re.sub(r'^\d+\.\s*', '', text).strip()
    
    # 使用句号分割文本，并提取第二部分
    parts = text.split('.')
    if 'http' in parts:
        return None
    if len(parts) > 1:
        title_part = parts[1].strip()  # 获取第二部分
        return title_part
    return text

def extract_dois_arxiv_urls(text):
    """ 从文本中提取DOI号、arXiv号或普通URL """
    text = re.sub(r'^\d+\.\s*', '', text).strip()
    author1=text.split(',')[0]
    dois = doi_pattern.findall(text)
    arxiv_ids = arxiv_pattern.findall(text)
    urls = url_pattern.findall(text)
    return author1,dois, arxiv_ids, urls
def construct_bibtex_cf(item):
    """
    构建 BibTeX 字符串。
    """
    title = item.get('title', ['No Title'])[0]
    doi = item.get('DOI', 'No DOI')
    journal = item.get('container-title', ['No Journal'])[0]
    volume = item.get('volume', 'No Volume')
    page = item.get('page', 'No Page')
    year = item['issued']['date-parts'][0][0]
    
    # Extract authors
    authors = item.get('author', [])
    author_list = " and ".join([f"{a.get('family', '')} {a.get('given', '')}" for a in authors])

    # Construct BibTeX entry
    bibtex_entry = f"""@article{{{doi.replace('/', '_')},
        title = {{{title}}},
        author = {{{author_list}}},
        journal = {{{journal}}},
        volume = {{{volume}}},
        pages = {{{page}}},
        year = {{{year}}},
        doi = {{{doi}}}
    }}"""
    return bibtex_entry

def fetch_bibtex_from_crossref(title=None,author1=None, doi=None):
    """
    从 CrossRef 获取文献的元数据，并返回 BibTeX 格式。
    使用标题和 DOI 进行检索，优先使用 DOI。
    """
    if title:
        search_url = f"https://api.crossref.org/works?query={title}&query.author={author1}&rows=1"
        response = requests.get(search_url)
        if response.status_code == 200:
            response_data = response.json()
            items = response_data.get('message', {}).get('items', [])
            
            if items:
                # Assume we take the first result
                return construct_bibtex_cf(items[0])
            else:
                return ""
        else:
            print(f"无法访问 CrossRef API，状态码: {response.status_code}")
            return ''
    elif doi:
        url = f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex"
        response = requests.get(url)
        if response.status_code == 200:
            response_data = response.json()
            if response_data['message']['total-results'] > 0:
                item = response_data.get('message')
                if item:
                    return construct_bibtex_cf(item)
                else:
                    return ""
    else:return ''

def fetch_bibtex_from_arxiv(title=None, arxiv_id=None):
    """
    从 arXiv API 获取文献的元数据，并返回 BibTeX 格式。
    使用标题和 arXiv ID 进行检索。
    """
    # 使用 arXiv API 查询
    encoded_title = quote(title)
    if len(title)>15:
        query_url = f'http://export.arxiv.org/api/query?search_query={encoded_title}&id_list={arxiv_id}&max_results=1'
    else:
        query_url = f'http://export.arxiv.org/api/query?id_list={arxiv_id}'
        
    try:
        with libreq.urlopen(query_url) as url:
            r = url.read()
            # 解析 XML
            root = ET.fromstring(r)
            
            # 提取文献信息
            entry = root.find('{http://www.w3.org/2005/Atom}entry')
            if entry is not None:
                # 提取标题
                title_element = entry.find('{http://www.w3.org/2005/Atom}title')
                title_text = title_element.text if title_element is not None else "No title found"

                # 提取摘要
                summary_element = entry.find('{http://www.w3.org/2005/Atom}summary')
                summary_text = summary_element.text if summary_element is not None else "No summary found"

                # 获取当前日期作为访问日期
                access_date = datetime.now().strftime('%Y-%m-%d')

                # 构建 BibTeX 字符串
                bibtex_entry = f"""@article{{arxiv:{arxiv_id},
                                title = {{{title_text}}},
                                url = {{{query_url}}},
                                note = {{{summary_text}}},
                                urldate = {{{access_date}}}
                                }}"""
                return bibtex_entry
            else:
                print(f"未找到条目{title,arxiv_id}")
                return ''
    except Exception as e:
        print(f"请求出错: {e}")
        return ''

def fetch_webpage_metadata(url):
    """ 从网页中提取元数据，并以 BibTeX 格式返回 """
    if 'arxiv.org' in url:
        print(f"跳过arXiv网页处理: {url}")
        return ''
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.title.string if soup.title else "No title found"
        description_tag = soup.find('meta', attrs={'name': 'description'})
        description = description_tag['content'] if description_tag and 'content' in description_tag.attrs else ""
        access_date = datetime.now().strftime('%Y-%m-%d')
        
        bibtex_entry = f"""@webpage{{webpage,
                        title = {{{title}}},
                        url = {{{url}}},
                        note = {{{description}}},
                        urldate = {{{access_date}}}
                        }}"""
        return bibtex_entry
    else:
        print(f"无法访问该网页{url}，状态码: {response.status_code}")
        return ''
    
def simplify_title_search(title):
    # 将标题按空格分割为词语
    words = title.split()
    words=['"'+w+'"[Title]' for w in words]
    simplified_search = " AND ".join(words)
    
    return simplified_search
def fetch_pubmed_metadata(title=None, pmid=None):
    """
    从 PubMed 获取文献的元数据，并返回 BibTeX 格式。
    使用标题和 PubMed ID (PMID) 进行检索，优先使用 PMID。
    """
    if pmid:
        # 使用 PMID 检索文献
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=xml"
        response = requests.get(url)
        time.sleep(2)
        if response.status_code == 200:
            return construct_bibtex_from_response(response.content,pmid)
        else:
            return f"错误: {response.status_code} - {response.text}"

    elif title:
        # 使用标题检索文献
        title =title.replace(' ','+')
        search_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={title}&field=title&retmode=xml'
        search_response = requests.get(search_url)
        time.sleep(2)
        if search_response.status_code == 200:
            root = ET.fromstring(search_response.content)
            id_list = root.find("IdList")
            if id_list is not None and id_list.findall("Id"):
                # 仅当 ID 列表非空时，提取第一个 ID
                pubmed_id = id_list.find("Id").text
                print(f"PubMed ID found: {pubmed_id}")
                return fetch_pubmed_metadata(pmid=pubmed_id[0])  # 使用第一个结果的 PMID
            else:
                print("No PubMed IDs found.")
                return None
                    

        else:
            print(f"错误: {search_response.status_code} - {search_response.text}")
            return ""
    
    return ""

def construct_bibtex_from_response(xml_content, pmid=None):
    """
    从 PubMed 响应中构建 BibTeX 字符串。
    """
    root = ET.fromstring(xml_content)
    docsum = root.find(".//DocSum")
    
    if docsum is not None:
        # 提取字段，处理可能为空的情况
        title_element = docsum.find(".//Item[@Name='Title']")
        title = title_element.text if title_element is not None else "无标题"
        
        doi_element = docsum.find(".//Item[@Name='DOI']")
        doi = doi_element.text if doi_element is not None else "无 DOI"
        
        journal_element = docsum.find(".//Item[@Name='Source']")
        journal = journal_element.text if journal_element is not None else "无期刊"
        
        volume_element = docsum.find(".//Item[@Name='Volume']")
        volume = volume_element.text if volume_element is not None else "无卷号"
        
        page_element = docsum.find(".//Item[@Name='Pages']")
        page = page_element.text if page_element is not None else "无页码"
        
        year_element = docsum.find(".//Item[@Name='PubDate']")
        year = year_element.text.split()[0] if year_element is not None else "无年份"
        
        # 提取作者列表
        authors = docsum.findall(".//Item[@Name='AuthorList']/Item[@Name='Author']")
        author_list = " and ".join([author.text for author in authors if author.text]) if authors else "无作者"

        # 构建 BibTeX 条目，包含 PMID
        bibtex_entry = f"""@article{{{doi.replace('/', '_')},
            title = {{{title}}},
            author = {{{author_list}}},
            journal = {{{journal}}},
            volume = {{{volume}}},
            pages = {{{page}}},
            year = {{{year}}},
            doi = {{{doi}}},
            pmid = {{{pmid}}}
        }}"""
        return bibtex_entry
    
    return ""
        
def save_bibtex(bibtex_entries, filename="output.bib"):
    """ 保存BibTeX条目到文件 """
    with open(filename, "w", encoding="utf-8") as f:
        for entry in bibtex_entries:
            f.write(entry + "\n\n")

def process_txt_file(file_path):
    """ 从txt文件中逐行读取内容，并提取DOI号、arXiv ID 和普通网页URL，获取BibTeX条目 """
    bibtex_entries = []
    with open(file_path, "r", encoding="utf-8") as file:
        total_lines = sum(1 for _ in open(file_path, 'r', encoding='utf-8'))  # 计算文件总行数
        file.seek(0)  # 将文件指针复位到文件开头

        for line in tqdm(file, total=total_lines, desc="Processing Lines", unit="line"):
            # 提取当前行中的DOI号、arXiv ID和URL
            author1,dois, arxiv_ids, urls = extract_dois_arxiv_urls(line)
            title=extract_title(line)
            # 遍历每个DOI，获取对应的BibTeX条目
            if title:
                if len(title)>15:
                    bibtex_entry = fetch_bibtex_from_crossref(title,author1)
                    if bibtex_entry:
                        if 'No Page' in bibtex_entry or 'No Volume' in bibtex_entry:
                            bibtex_entry_med=fetch_pubmed_metadata(title=title)
                            if bibtex_entry_med:
                                bibtex_entries.append(bibtex_entry_med)
                            else:
                                bibtex_entries.append(bibtex_entry)
            else:
                if dois:
                    bibtex_entry = fetch_bibtex_from_crossref(dois[0])
                    if bibtex_entry:
                        bibtex_entries.append(bibtex_entry)
            
            # 遍历每个arXiv ID，获取对应的BibTeX条目
            for arxiv_id in arxiv_ids:
                bibtex_entry = fetch_bibtex_from_arxiv(title,arxiv_id)
                if bibtex_entry:
                    bibtex_entries.append(bibtex_entry)
            
            # 遍历每个普通URL，尝试提取网页元数据并生成BibTeX条目
            for url in urls:
                bibtex_entry = fetch_webpage_metadata(url)
                if bibtex_entry:
                    bibtex_entries.append(bibtex_entry)
    
    # 将所有BibTeX条目保存到文件
    save_bibtex(bibtex_entries)

# 示例使用：
txt_file_path = "article.txt"  # 替换为你的txt文件路径
process_txt_file(txt_file_path)
