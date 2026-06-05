export function formatDate(dateStr: string | null | undefined, timezone?: string): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
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
