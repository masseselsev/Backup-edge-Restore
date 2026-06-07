export function formatDate(dateStr: string | null | undefined, timezone?: string): string {
  if (!dateStr) return '';
  // If the date string doesn't specify a timezone offset, assume UTC (add 'Z')
  let normalizedDateStr = dateStr;
  if (
    !dateStr.endsWith('Z') && 
    !dateStr.includes('+') && 
    !/[-+]\d{2}:?\d{2}$/.test(dateStr)
  ) {
    normalizedDateStr = dateStr.replace(' ', 'T') + 'Z';
  }

  const date = new Date(normalizedDateStr);
  if (isNaN(date.getTime())) return '';

  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    second: 'numeric',
  };

  if (timezone && timezone !== 'Browser Local') {
    try {
      options.timeZone = timezone;
    } catch (e) {
      console.warn(`Invalid timezone specified: ${timezone}`, e);
    }
  }

  return new Intl.DateTimeFormat(undefined, options).format(date);
}
