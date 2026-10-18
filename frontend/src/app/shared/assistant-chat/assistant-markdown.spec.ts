import { describe, expect, it } from 'vitest';
import { renderAssistantMarkdown } from './assistant-markdown';

describe('renderAssistantMarkdown', () => {
  it('transforma tabela em cartões legíveis no painel', () => {
    const html = renderAssistantMarkdown(
      '| SKU | Saldo | Situação |\n| --- | --- | --- |\n| F-1 | 1 | Abaixo |',
    );
    expect(html).toContain('md-records');
    expect(html).toContain('<h4>F-1</h4>');
    expect(html).toContain('<dt>Saldo</dt><dd>1</dd>');
    expect(html).not.toContain('| --- |');
  });

  it('renderiza listas e negrito sem exibir marcação', () => {
    const html = renderAssistantMarkdown('- **Atenção:** saldo baixo\n- Repor hoje');
    expect(html).toContain('<ul>');
    expect(html).toContain('<strong>Atenção:</strong>');
    expect(html).not.toContain('- **');
  });

  it('escapa HTML vindo do modelo', () => {
    const html = renderAssistantMarkdown('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
  });
});
