export interface AnswerParts {
  /** Markdown body without the follow-up list or the sources footer. */
  body: string;
  /** Follow-up questions from the "Next questions" section, plain text. */
  next: string[];
  /** Footer lines from the agent ("Sources: …", "Unavailable: …"), plain text. */
  footer: string[];
}

const HEADING = /^\s*(?:#{1,6}\s*|\*\*)?next questions(?:\*\*)?:?\s*$/i;
const LIST_ITEM = /^\s*(?:[-*+]|\d+[.)])\s+(.+)$/;

const plain = (s: string) =>
  s.replace(/\*\*|__|`/g, '').replace(/^\*(.*)\*$/, '$1').replace(/^["“](.*)["”]$/, '$1').trim();

/**
 * Splits the agent's markdown so the UI can render follow-ups as buttons and
 * the sources line as a footer. Falls back to the untouched text when the
 * expected sections are missing.
 */
export function splitAnswer(text: string): AnswerParts {
  let body = text;
  let footer: string[] = [];

  const foot = body.match(/\n+-{3,}\s*\n+(\*?Sources:[\s\S]*)$/);
  if (foot) {
    footer = foot[1].split('\n').map((l) => plain(l)).filter(Boolean);
    body = body.slice(0, foot.index);
  }

  const lines = body.split('\n');
  const start = lines.findIndex((l) => HEADING.test(l));
  if (start === -1) return { body: body.trimEnd(), next: [], footer };

  const next: string[] = [];
  let end = start + 1;
  for (; end < lines.length; end++) {
    const line = lines[end];
    const item = line.match(LIST_ITEM);
    if (item) next.push(plain(item[1]));
    else if (line.trim() && next.length) break;
    else if (line.trim().startsWith('#')) break;
  }
  if (!next.length) return { body: body.trimEnd(), next: [], footer };

  body = [...lines.slice(0, start), ...lines.slice(end)].join('\n').trimEnd();
  return { body, next, footer };
}
