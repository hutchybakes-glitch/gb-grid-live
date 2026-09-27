// Display helpers. All data is UTC; convert to UK time only here, for display.

const TZ = 'Europe/London'

const timeFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit' })
const dayTimeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, weekday: 'short', hour: '2-digit', minute: '2-digit',
})
const dateTimeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
})
const dayFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, weekday: 'long' })
const zoneFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, timeZoneName: 'short' })

/** "14:30" in UK local time. */
export function ukTime(t: number | string): string {
  return timeFmt.format(new Date(t))
}

/** "Sun 14:30" in UK local time. */
export function ukDayTime(t: number | string): string {
  return dayTimeFmt.format(new Date(t))
}

/** "27 Sept, 14:30" in UK local time. */
export function ukDateTime(t: number | string): string {
  return dateTimeFmt.format(new Date(t))
}

/** "Sunday". */
export function ukDay(t: number | string): string {
  return dayFmt.format(new Date(t))
}

/** "BST" or "GMT", so labels say which UK time is in force. */
export function ukZone(t: number | string = Date.now()): string {
  const part = zoneFmt.formatToParts(new Date(t)).find((p) => p.type === 'timeZoneName')
  return part?.value === 'GMT+1' ? 'BST' : (part?.value ?? 'UK time')
}

/** Round to a whole number with thousands separators. */
export function whole(n: number): string {
  return Math.round(n).toLocaleString('en-GB')
}

/** Grams to a friendly g/kg string. */
export function grams(g: number): string {
  return Math.abs(g) >= 1000 ? `${(g / 1000).toFixed(1)} kg` : `${Math.round(g)} g`
}
