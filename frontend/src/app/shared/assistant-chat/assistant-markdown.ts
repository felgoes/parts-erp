const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

function inline(value: string): string {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function isTableStart(lines: string[], index: number): boolean {
  const header = lines[index]?.trim() ?? '';
  const separator = lines[index + 1]?.trim() ?? '';
  return (
    header.includes('|') &&
    /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(separator)
  );
}

function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function table(lines: string[], start: number): { html: string; next: number } {
  const headers = cells(lines[start]);
  let index = start + 2;
  const rows: string[][] = [];
  while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
    rows.push(cells(lines[index]));
    index += 1;
  }
  const cards = rows
    .filter((row) => row.some((cell) => cell))
    .map((row) => {
      const title = row[0] || headers[0] || 'Registro';
      const fields = headers
        .slice(1)
        .map((header, position) => {
          const value = row[position + 1] ?? '';
          if (!value) return '';
          return `<div><dt>${inline(header)}</dt><dd>${inline(value)}</dd></div>`;
        })
        .join('');
      return `<article class="md-record"><h4>${inline(title)}</h4><dl>${fields}</dl></article>`;
    })
    .join('');
  return { html: `<div class="md-records">${cards}</div>`, next: index };
}

function list(lines: string[], start: number, ordered: boolean): { html: string; next: number } {
  const pattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/;
  const items: string[] = [];
  let index = start;
  while (index < lines.length && pattern.test(lines[index])) {
    items.push(lines[index].replace(pattern, ''));
    index += 1;
  }
  const tag = ordered ? 'ol' : 'ul';
  return {
    html: `<${tag}>${items.map((item) => `<li>${inline(item)}</li>`).join('')}</${tag}>`,
    next: index,
  };
}

/**
 * Renderiza apenas o subconjunto de Markdown que o assistente usa. O HTML é escapado antes
 * das substituições e o Angular ainda aplica a sanitização padrão ao inserir o resultado.
 */
export function renderAssistantMarkdown(source: string): string {
  const lines = (source || '').replace(/\r\n/g, '\n').split('\n');
  const html: string[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (isTableStart(lines, index)) {
      const parsed = table(lines, index);
      html.push(parsed.html);
      index = parsed.next;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const parsed = list(lines, index, false);
      html.push(parsed.html);
      index = parsed.next;
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const parsed = list(lines, index, true);
      html.push(parsed.html);
      index = parsed.next;
      continue;
    }
    if (/^#{1,6}\s+/.test(line)) {
      html.push(`<p class="md-heading">${inline(line.replace(/^#{1,6}\s+/, ''))}</p>`);
      index += 1;
      continue;
    }
    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !isTableStart(lines, index) &&
      !/^\s*[-*]\s+/.test(lines[index]) &&
      !/^\s*\d+[.)]\s+/.test(lines[index]) &&
      !/^#{1,6}\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    html.push(`<p>${inline(paragraph.join(' '))}</p>`);
  }
  return html.join('');
}
