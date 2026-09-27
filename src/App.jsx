import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DOMPurify from 'dompurify'

const API_BASE_URL = 'http://localhost:8000'

const CATEGORY_FILTERS = [
  'ACTION_REQUIRED',
  'OPPORTUNITIES',
  'EVENTS',
  'ALERTS',
  'INFORMATION',
]

const CATEGORY_LABELS = {
  ACTION_REQUIRED: 'Action Required',
  OPPORTUNITIES: 'Opportunities',
  EVENTS: 'Events',
  ALERTS: 'Alerts',
  INFORMATION: 'Information',
}

const CATEGORY_STYLES = {
  ACTION_REQUIRED: { badge: 'bg-[#fff0dc] text-[#ba7628]', bar: 'bg-[#d18a25]' },
  OPPORTUNITIES: { badge: 'bg-[#e7f2e8] text-[#4f8060]', bar: 'bg-[#3f9a69]' },
  EVENTS: { badge: 'bg-[#e6eef7] text-[#55789b]', bar: 'bg-[#4e82bc]' },
  ALERTS: { badge: 'bg-[#fae8e5] text-[#b85a50]', bar: 'bg-[#d15d4e]' },
  INFORMATION: { badge: 'bg-[#edf0f0] text-[#667278]', bar: 'bg-[#6f858f]' },
}

const MAX_REPLY_ATTACHMENTS = 10
const MAX_REPLY_ATTACHMENT_BYTES = 10 * 1024 * 1024
const MAX_REPLY_TOTAL_BYTES = 25 * 1024 * 1024
const BLOCKED_REPLY_EXTENSIONS = new Set(['.exe', '.bat', '.cmd', '.com', '.js', '.ps1', '.sh', '.vbs', '.php'])
const LOGOUT_ERROR_MESSAGE = 'Unable to log out right now. Please try again.'
const MOBILE_EMAIL_HTML_CLASSES = [
  'max-[767px]:box-border max-[767px]:w-full max-[767px]:min-w-0 max-[767px]:max-w-full max-[767px]:text-[0.8125rem] max-[767px]:leading-[1.5] max-[767px]:[overflow-wrap:anywhere]',
  'max-[767px]:[&_*]:!box-border max-[767px]:[&_*]:!min-w-0 max-[767px]:[&_*]:!max-w-full max-[767px]:[&_*]:!whitespace-normal max-[767px]:[&_*]:!break-words max-[767px]:[&_*]:!flex-wrap max-[767px]:[&_*]:!text-[0.8125rem] max-[767px]:[&_*]:!leading-[1.5]',
  'max-[767px]:[&_div]:!min-w-0 max-[767px]:[&_div]:!mx-0 max-[767px]:[&_span]:!min-w-0 max-[767px]:[&_li]:!min-w-0',
  'max-[767px]:[&_td]:!min-w-0 max-[767px]:[&_td]:!w-auto max-[767px]:[&_th]:!min-w-0 max-[767px]:[&_th]:!w-auto',
  'max-[767px]:[&_table]:!w-full max-[767px]:[&_table]:!max-w-full max-[767px]:[&_table]:!table-fixed',
  'max-[767px]:[&_a]:inline-block max-[767px]:[&_a]:align-middle max-[767px]:[&_a]:max-w-full max-[767px]:[&_button]:max-w-full',
  'max-[767px]:[&_img]:!max-w-full max-[767px]:[&_img]:!h-auto max-[767px]:[&_video]:!max-w-full max-[767px]:[&_video]:!h-auto max-[767px]:[&_svg]:!max-w-full max-[767px]:[&_svg]:!h-auto max-[767px]:[&_iframe]:!max-w-full max-[767px]:[&_object]:!max-w-full max-[767px]:[&_embed]:!max-w-full',
  'max-[767px]:[&_h1]:!my-2 max-[767px]:[&_h1]:!text-[1.375rem] max-[767px]:[&_h1]:!leading-[1.25] max-[767px]:[&_h2]:!my-2 max-[767px]:[&_h2]:!text-[1.25rem] max-[767px]:[&_h2]:!leading-[1.25]',
  'max-[767px]:[&_h3]:!my-2 max-[767px]:[&_h3]:!text-[1.125rem] max-[767px]:[&_h3]:!leading-[1.25] max-[767px]:[&_h4]:!my-2 max-[767px]:[&_h4]:!text-[1rem] max-[767px]:[&_h4]:!leading-[1.25] max-[767px]:[&_h5]:!my-2 max-[767px]:[&_h5]:!text-[0.9375rem] max-[767px]:[&_h6]:!my-2 max-[767px]:[&_h6]:!text-[0.875rem]',
  'max-[767px]:[&_p]:!my-2 max-[767px]:[&_ul]:!my-2 max-[767px]:[&_ol]:!my-2 max-[767px]:[&_pre]:max-w-full max-[767px]:[&_pre]:break-words max-[767px]:[&_pre]:whitespace-pre-wrap max-[767px]:[&_blockquote]:mx-2',
].join(' ')

function getReplyPlainText(value) {
  return (value || '')
    .replace(/<br\s*\/?>(\n)?/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .trim()
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function hasValidRecipients(value) {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .every((part) => /^([^<>]+<)?\S+@\S+\.\S+>?$/.test(part))
}

function formatReceivedDate(value) {
  if (!value) return 'No date'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function getEmailBodyText(email) {
  if (email.html_body) {
    return new DOMParser().parseFromString(email.html_body, 'text/html').body.textContent || ''
  }
  return email.original_body ?? email.body ?? email.full_body ?? email.snippet ?? ''
}

function EmailBody({ email, className, htmlClassName }) {
  if (email.html_body) {
    return <div className={`${htmlClassName || className} html-email-content font-[Arial,sans-serif] text-[13px] leading-normal whitespace-normal text-[#222] [overflow-wrap:normal] ${MOBILE_EMAIL_HTML_CLASSES}`} dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(email.html_body) }} />
  }
  return <div className={`${className} whitespace-pre-wrap`}>{email.original_body ?? email.body ?? email.full_body ?? email.snippet ?? ''}</div>
}

function GoogleLogo() {
  return (
    <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M21.35 12.27c0-.79-.07-1.55-.2-2.27H12v4.3h5.24a4.48 4.48 0 0 1-1.94 2.94v2.45h3.14c1.84-1.69 2.91-4.18 2.91-7.42Z" />
      <path fill="#34A853" d="M12 21.5c2.63 0 4.84-.87 6.45-2.36l-3.14-2.45c-.87.58-1.98.92-3.31.92-2.54 0-4.7-1.72-5.47-4.03H3.28v2.53A9.74 9.74 0 0 0 12 21.5Z" />
      <path fill="#FBBC05" d="M6.53 13.58a5.86 5.86 0 0 1 0-3.16V7.89H3.28a9.5 9.5 0 0 0 0 8.22l3.25-2.53Z" />
      <path fill="#EA4335" d="M12 6.39c1.43 0 2.71.49 3.72 1.46l2.79-2.79C16.84 3.5 14.63 2.5 12 2.5a9.74 9.74 0 0 0-8.72 5.39l3.25 2.53C7.3 8.11 9.46 6.39 12 6.39Z" />
    </svg>
  )
}

function CategoryNavigation({ selectedCategory, categoryCounts, onSelect, ariaLabel = 'Sidebar navigation', drawer = false }) {
  const compactClasses = drawer ? '' : 'max-[900px]:grid-cols-1 max-[900px]:justify-items-center max-[560px]:hidden'

  return (
    <nav className="grid gap-[0.2rem]" aria-label={ariaLabel}>
      {CATEGORY_FILTERS.map((category) => (
        <button type="button" className={`grid grid-cols-[1.4rem_minmax(0,1fr)_auto] items-center gap-[0.3rem] rounded-[7px] px-[0.55rem] py-[0.58rem] text-left text-[0.75rem] font-medium text-[#626d68] transition-colors hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] ${compactClasses} ${selectedCategory === category ? 'bg-[#cfe9df] text-[#174f47] max-[560px]:grid max-[560px]:w-[2.3rem]' : ''} ${drawer ? 'max-[560px]:w-full' : ''}`} key={category} onClick={() => onSelect(category)}>
          <span className="text-[0.9rem] text-[#7c8781]">{category === 'ACTION_REQUIRED' ? '◷' : category === 'OPPORTUNITIES' ? '↗' : category === 'EVENTS' ? '□' : category === 'ALERTS' ? '△' : '▯'}</span>
          {CATEGORY_LABELS[category]} <b className={`text-[0.65rem] font-medium text-[#9ba49f] ${drawer ? '' : 'max-[900px]:hidden'}`}>{categoryCounts[category]}</b>
        </button>
      ))}
    </nav>
  )
}

function EmailCard({ email, onOpen, onReply, selected, expanded }) {
  const analysis = email.analysis || {}
  const category = analysis.category || analysis.primary_category || 'INFORMATION'
  const senderName = email.sender_name || email.sender || 'Unknown sender'
  const senderAddress = email.sender && email.sender.trim().toLowerCase() !== senderName.trim().toLowerCase() ? email.sender : ''
  return (
    <article className={`min-w-0 max-w-full cursor-pointer bg-[#faf9f6] px-4 py-[0.7rem] transition-colors hover:bg-[#e1efe9] active:bg-[#c8e4da] max-[767px]:px-[0.8rem] max-[767px]:py-[0.85rem] ${selected ? 'bg-[#cfe9df] shadow-[inset_3px_0_#0f806f]' : ''} ${expanded ? 'bg-[#e1efe9]' : ''}`}>
      <div className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-start gap-[0.7rem] focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#176b61] max-[767px]:grid-cols-[2.15rem_minmax(0,1fr)_auto] max-[767px]:gap-[0.65rem]" role="button" tabIndex="0" onClick={() => onOpen(email)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onOpen(email) } }}>
        <span className={`grid h-8 w-8 place-items-center rounded-full text-[0.65rem] font-semibold max-[767px]:h-[2.15rem] max-[767px]:w-[2.15rem] ${CATEGORY_STYLES[category]?.badge || CATEGORY_STYLES.INFORMATION.badge}`}>{senderName.charAt(0).toUpperCase()}</span>
        <div className="min-w-0">
          <p className="text-[0.74rem] font-semibold text-[#263a34] max-[767px]:text-[0.78rem]">{senderName}</p>
          <h3 className="mt-[0.15rem] mb-1 overflow-hidden text-ellipsis whitespace-nowrap text-[0.77rem] font-bold text-[#182a25] max-[767px]:mt-[0.2rem] max-[767px]:whitespace-normal max-[767px]:text-[0.82rem] max-[767px]:leading-[1.35]">{email.subject || '(No subject)'}</h3>
        </div>
        <div className="grid justify-items-end gap-[0.55rem] max-[767px]:gap-[0.45rem]">
          <span className="whitespace-nowrap text-[0.62rem] font-medium text-[#65766f] max-[767px]:text-[0.66rem]">{formatReceivedDate(email.received_at)}</span>
          <span className={`max-w-28 overflow-hidden text-ellipsis whitespace-nowrap rounded px-[0.4rem] py-[0.18rem] text-[0.6rem] ${CATEGORY_STYLES[category]?.badge || CATEGORY_STYLES.INFORMATION.badge}`}>{CATEGORY_LABELS[category] || category}</span>
        </div>
      </div>
      {expanded && (
        <div className="hidden w-full min-w-0 max-w-full px-[0.15rem] pt-[0.65rem] pb-[0.2rem] max-[767px]:block inline-email-body">
          {senderAddress && <div className="grid gap-1 text-[0.72rem] text-[#354b43]"><span className="break-all text-[0.66rem] text-[#65776f]">{senderAddress}</span></div>}
          {analysis.reason && <div className="mt-3 rounded-r-md border-l-[3px] border-[#0f806f] bg-[#dceee9] px-[0.65rem] py-[0.6rem] text-[#176b61]"><strong className="text-[0.68rem]">◎ &nbsp;Why this matters</strong><p className="mt-1 text-[0.68rem] leading-[1.45] text-[#50675e]">{analysis.reason}</p></div>}
          <EmailBody email={email} className="mt-[0.85rem] w-full min-w-0 max-w-full break-words text-[0.8rem] leading-[1.55] whitespace-pre-wrap text-[#30423a] [overflow-wrap:anywhere]" htmlClassName="mt-[0.85rem] w-full min-w-0 max-w-full break-words [overflow-wrap:anywhere]" />
          {email.attachments?.length > 0 && <div className="mt-3 flex flex-wrap gap-[0.4rem]">{email.attachments.map((attachment) => <span className="max-w-full break-words rounded border border-[#c9dad4] bg-[#f8fbf9] px-2 py-[0.42rem] text-[0.65rem] text-[#4c655b]" key={attachment.id || attachment.name}>{attachment.name || attachment.filename}</span>)}</div>}
          <div className="mt-4 flex flex-wrap items-center gap-3"><button type="button" className="min-h-[2.4rem] rounded-md bg-[#176b61] px-3 py-[0.55rem] text-[0.76rem] text-white transition-colors hover:bg-[#0f806f] active:bg-[#0b574f] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#176b61]" onClick={(event) => { event.stopPropagation(); onReply(email) }}>↩ &nbsp; Reply</button><a className="rounded px-1.5 py-1 text-[0.68rem] text-[#176b61] no-underline hover:bg-[#d6ebe4] hover:text-[#174f47] active:bg-[#b9ddcf] focus-visible:outline-2 focus-visible:outline-[#176b61]" href={email.gmail_url || '#'} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>Open in Gmail ↗</a></div>
        </div>
      )}
    </article>
  )
}

function ProfileControl({ user, open, onToggle, onLogout, loggingOut, selectedCategory, categoryCounts, onSelectCategory }) {
  const displayName = user.name?.trim() || user.email?.trim() || 'Google user'
  const initial = displayName.match(/[\p{L}\p{N}]/u)?.[0]?.toLocaleUpperCase() || 'G'

  return (
    <div className="profile-control relative shrink-0">
      <button type="button" className={`group inline-flex min-w-0 items-center gap-2 rounded-md bg-transparent px-[0.35rem] py-[0.2rem] text-[0.75rem] text-[#34403b] transition-colors hover:bg-[#d6ebe4] active:bg-[#b9ddcf] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] max-[767px]:p-0 ${open ? 'bg-[#d6ebe4] text-[#174f47]' : ''}`} aria-label="Open profile" aria-haspopup="dialog" aria-expanded={open} onClick={onToggle}>
        <span className="grid h-[2.2rem] w-[2.2rem] shrink-0 place-items-center overflow-hidden rounded-full border border-[#d9e2dc] bg-[#e5f0ed] text-[0.78rem] font-bold text-[#176b61] transition-colors group-hover:bg-[#d8ebe6] max-[767px]:h-[2.35rem] max-[767px]:w-[2.35rem]" aria-hidden="true">{initial}</span>
        <span className="max-w-40 overflow-hidden text-ellipsis whitespace-nowrap max-[767px]:hidden">{displayName}</span>
      </button>
      {open && (
        <>
          <aside className="absolute right-0 top-full z-40 mt-2 hidden w-[min(18rem,calc(100vw-2rem))] min-w-0 flex-col gap-4 overflow-x-hidden rounded-lg border border-[rgba(99,117,108,0.16)] bg-[#fffefa] p-4 shadow-[0_12px_28px_rgba(40,47,43,0.14)] min-[768px]:flex" role="dialog" aria-label="User profile">
            <div className="grid min-w-0 gap-[0.2rem]">
              <strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[0.8rem] text-[#263a34]">{displayName}</strong>
              {user.email && <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[0.7rem] text-[#78847e]">{user.email}</span>}
            </div>
            <button type="button" className="w-full rounded-md bg-[#dceee8] p-[0.65rem] text-left text-[0.73rem] font-medium text-[#174f47] transition-colors hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:cursor-wait disabled:opacity-60" onClick={onLogout} disabled={loggingOut}>
              {loggingOut ? 'Logging out...' : 'Log out'}
            </button>
          </aside>
          <aside className="fixed inset-y-0 right-0 z-40 flex min-h-svh w-[min(24rem,92vw)] min-w-0 flex-col overflow-x-hidden border-l border-[rgba(99,117,108,0.12)] bg-[#fffefa] p-5 max-[767px]:top-0 max-[767px]:w-1/2 max-[767px]:max-w-[50vw] max-[767px]:p-3 min-[768px]:hidden" role="dialog" aria-label="User profile">
          <h2 className="mb-[1.1rem] hidden text-[0.95rem] font-semibold text-[#263a34] max-[767px]:block">Profile</h2>
          <div className="hidden min-w-0 flex-col items-center gap-[0.6rem] px-0 pt-[0.4rem] pb-[1.2rem] text-center max-[767px]:flex">
            <span className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-full border border-[#d9e2dc] bg-[#e5f0ed] text-[0.78rem] font-bold text-[#176b61]" aria-hidden="true">{initial}</span>
            <div className="grid min-w-0 max-w-full gap-[0.2rem]"><strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[0.8rem] text-[#263a34]">{displayName}</strong><span className="overflow-hidden text-ellipsis whitespace-nowrap text-[0.7rem] text-[#78847e]">{user.email}</span></div>
          </div>
          <div className="hidden max-[767px]:block"><CategoryNavigation selectedCategory={selectedCategory} categoryCounts={categoryCounts} onSelect={onSelectCategory} ariaLabel="Dashboard navigation" drawer /></div>
          <button type="button" className="mt-auto w-full rounded-md bg-[#dceee8] p-[0.65rem] text-left text-[0.73rem] font-medium text-[#174f47] transition-colors hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:cursor-wait disabled:opacity-60" onClick={onLogout} disabled={loggingOut}>
            {loggingOut ? 'Logging out…' : 'Log out'}
          </button>
          </aside>
        </>
      )}
    </div>
  )
}

function EmailDetailPanel({ email, onReply }) {
  if (!email) return <section className="grid min-w-0 place-items-center overflow-y-auto bg-[#fffefa] text-[0.8rem] text-[#929b96]">Select an email to view it.</section>

  const analysis = email.analysis || {}
  const category = analysis.category || analysis.primary_category || 'INFORMATION'
  return (
    <section className="min-w-0 overflow-y-auto bg-[#fffefa] max-[900px]:hidden" aria-label="Selected email">
      <div className="max-w-[760px] px-[1.4rem] pt-[1.7rem] pb-8">
        <span className={`rounded px-[0.55rem] py-[0.28rem] text-[0.65rem] ${CATEGORY_STYLES[category]?.badge || CATEGORY_STYLES.INFORMATION.badge}`}>{CATEGORY_LABELS[category] || category}</span>
        <h2 className="mt-[0.85rem] text-[clamp(1.55rem,2.2vw,2rem)] font-medium leading-[1.15] tracking-[-0.03em] text-[#182a25]">{email.subject || '(No subject)'}</h2>
        <div className="mt-[1.15rem] flex items-center gap-[0.65rem]">
          <span className={`grid h-8 w-8 place-items-center rounded-full text-[0.65rem] font-semibold ${CATEGORY_STYLES[category]?.badge || CATEGORY_STYLES.INFORMATION.badge}`}>{(email.sender_name || email.sender || '?').charAt(0).toUpperCase()}</span>
          <div className="grid gap-[0.2rem]"><strong className="text-[0.76rem] text-[#33403b]">{email.sender_name || email.sender || 'Unknown sender'}</strong><span className="text-[0.66rem] text-[#8c9690]">{email.sender || 'No sender email'} · {formatReceivedDate(email.received_at)}</span></div>
        </div>
        {analysis.reason && <div className="mt-5 rounded-md border border-[#d8e8e3] bg-[#e9f3f0] p-3 text-[#2f6a60]"><strong className="text-[0.72rem]">◎ &nbsp;Why this matters</strong><p className="mt-1 text-[0.72rem] leading-normal text-[#6d7c76]">{analysis.reason}</p></div>}
        <EmailBody email={email} className="mt-5 whitespace-pre-wrap text-[0.84rem] leading-[1.7] text-[#33443d] [overflow-wrap:anywhere]" htmlClassName="mt-5 whitespace-normal" />
        {email.attachments?.length > 0 && <div className="mt-6 text-[0.7rem] text-[#68746e]"><strong>{email.attachments.length} attachments</strong><div className="mt-2 flex flex-wrap gap-2">{email.attachments.map((attachment) => <span className="rounded-md border border-[#d9d9d2] bg-[#f8f7f3] px-[0.7rem] py-[0.55rem]" key={attachment.id || attachment.name}>{attachment.name || attachment.filename}</span>)}</div></div>}
        <div className="mt-6 flex items-center gap-3"><button type="button" className="rounded-md bg-[#176b61] px-4 py-[0.65rem] text-[0.76rem] text-white transition-colors hover:bg-[#0f806f] active:bg-[#0b574f] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#176b61]" onClick={() => onReply(email)}>↩ &nbsp; Reply</button><a className="rounded px-1.5 py-1 text-[0.74rem] text-[#55716a] no-underline hover:bg-[#d6ebe4] hover:text-[#174f47] active:bg-[#b9ddcf] focus-visible:outline-2 focus-visible:outline-[#176b61]" href={email.gmail_url || '#'} target="_blank" rel="noreferrer">Open in Gmail ↗</a></div>
      </div>
    </section>
  )
}

function EmailLoadingVisualization() {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4 py-8 text-center text-[#738078]" role="status" aria-live="polite">
      <div className="relative mb-5 h-36 w-52 max-[900px]:scale-90 max-[767px]:mb-4 max-[767px]:h-28 max-[767px]:w-40 max-[767px]:scale-100" aria-hidden="true">
        <div className="absolute bottom-3 left-1/2 h-14 w-32 -translate-x-1/2 rounded-xl border border-[#cfe3dc] bg-[#e9f3f0]" />
        <div className="absolute bottom-5 left-1/2 z-10 flex h-10 w-28 -translate-x-1/2 items-center justify-center rounded-lg border border-[#d8e5df] bg-[#fffefa] shadow-sm">
          <svg className="h-6 w-6 text-[#176b61]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
            <path d="m5 7 7 5 7-5M5 17l5-5m9 5-5-5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div className="animate-email-arrival motion-reduce:animate-none absolute top-3 left-1/2 z-20 flex h-11 w-16 -translate-x-1/2 flex-col gap-1.5 rounded-md border border-[#d1e4dc] bg-white p-2 shadow-[0_5px_12px_rgba(37,45,41,0.08)]">
          <span className="h-1 w-8 rounded-full bg-[#9abeb2]" />
          <span className="h-1 w-full rounded-full bg-[#d5e5df]" />
          <span className="h-1 w-3/4 rounded-full bg-[#d5e5df]" />
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-[0.9rem] font-semibold text-[#34433d]">Preparing your inbox</p>
        <p className="text-xs text-[#7a8780]">Fetching and organizing messages</p>
      </div>
    </div>
  )
}

function App() {
  const [user, setUser] = useState(null)
  const [emails, setEmails] = useState([])
  const [loadingUser, setLoadingUser] = useState(true)
  const [loadingEmails, setLoadingEmails] = useState(true)
  const [loggingOut, setLoggingOut] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState(CATEGORY_FILTERS[0])
  const [selectedEmail, setSelectedEmail] = useState(null)
  const [expandedEmailId, setExpandedEmailId] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 767px)').matches)
  const [profileOpen, setProfileOpen] = useState(false)
  const [replyEmail, setReplyEmail] = useState(null)
  const [replyBody, setReplyBody] = useState('')
  const [replyTo, setReplyTo] = useState('')
  const [replyCc, setReplyCc] = useState('')
  const [replyBcc, setReplyBcc] = useState('')
  const [replySubject, setReplySubject] = useState('')
  const [showCcBcc, setShowCcBcc] = useState(false)
  const [replyAttachments, setReplyAttachments] = useState([])
  const [replyError, setReplyError] = useState('')
  const [sendingReply, setSendingReply] = useState(false)
  const [isDraggingAttachment, setIsDraggingAttachment] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [logoutError, setLogoutError] = useState('')
  const replyEditorRef = useRef(null)
  const attachmentInputRef = useRef(null)
  const autoSyncUserRef = useRef(null)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 767px)')
    const updateViewport = (event) => setIsMobile(event.matches)

    mediaQuery.addEventListener('change', updateViewport)
    return () => mediaQuery.removeEventListener('change', updateViewport)
  }, [])

  useEffect(() => {
    if (!profileOpen) return undefined

    const closeProfile = (event) => {
      if (event.type === 'pointerdown' && !event.target.closest?.('.profile-control')) setProfileOpen(false)
      if (event.key === 'Escape') setProfileOpen(false)
    }

    document.addEventListener('pointerdown', closeProfile)
    document.addEventListener('keydown', closeProfile)
    return () => {
      document.removeEventListener('pointerdown', closeProfile)
      document.removeEventListener('keydown', closeProfile)
    }
  }, [profileOpen])

  const emailCount = useMemo(() => emails.length, [emails])
  const categoryCounts = useMemo(() => {
    const counts = Object.fromEntries(CATEGORY_FILTERS.map((category) => [category, 0]))

    emails.forEach((email) => {
      const category = email.analysis?.category || email.analysis?.primary_category
      if (category && counts[category] !== undefined) counts[category] += 1
    })

    return counts
  }, [emails])
  const visibleEmails = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase()
    return emails.filter((email) => {
      const category = email.analysis?.category || email.analysis?.primary_category
      if (!query && category !== selectedCategory) return false
      if (!query) return true
      return [email.sender_name, email.sender, email.subject, getEmailBodyText(email)]
        .some((value) => String(value || '').toLocaleLowerCase().includes(query))
    })
  }, [emails, searchQuery, selectedCategory])
  const activeEmail = visibleEmails.includes(selectedEmail) ? selectedEmail : visibleEmails[0]

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authStatus = params.get('auth')

    if (authStatus === 'success') {
      window.history.replaceState({}, '', window.location.pathname)
    }

    if (authStatus === 'error') {
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  const fetchCurrentUser = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
        credentials: 'include',
      })

      if (!response.ok) {
        setUser(null)
        return
      }

      const payload = await response.json()
      setUser(payload)
    } catch (error) {
      setUser(null)
    } finally {
      setLoadingUser(false)
    }
  }

  const fetchEmails = async () => {
    try {
      setLoadingEmails(true)
      setErrorMessage('')

      const response = await fetch(`${API_BASE_URL}/api/emails?limit=30&include_analysis=true`, {
        credentials: 'include',
      })

      if (!response.ok) {
        if (response.status === 401) {
          setUser(null)
          return
        }

        throw new Error('Unable to load your inbox right now.')
      }

      const payload = await response.json()
      setEmails(payload)
    } catch (error) {
      setErrorMessage(error.message || 'Unable to load your inbox right now.')
    } finally {
      setLoadingEmails(false)
    }
  }

  useEffect(() => {
    fetchCurrentUser()
  }, [])

  const handleGoogleLogin = () => {
    window.location.href = `${API_BASE_URL}/api/auth/google`
  }

  const handleLogout = async () => {
    if (loggingOut) return

    try {
      setLoggingOut(true)
      setLogoutError('')
      setErrorMessage((current) => current === LOGOUT_ERROR_MESSAGE ? '' : current)
      const response = await fetch(`${API_BASE_URL}/api/auth/disconnect`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!response.ok) throw new Error(LOGOUT_ERROR_MESSAGE)
      setLogoutError('')
      setErrorMessage((current) => current === LOGOUT_ERROR_MESSAGE ? '' : current)
      setProfileOpen(false)
      setUser(null)
    } catch {
      setLogoutError(LOGOUT_ERROR_MESSAGE)
    } finally {
      setLoggingOut(false)
    }
  }

  const handleSyncGmail = async () => {
    try {
      setErrorMessage('')

      const response = await fetch(`${API_BASE_URL}/api/gmail/sync`, {
        method: 'POST',
        credentials: 'include',
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        const message = payload.detail || 'Gmail sync failed.'
        throw new Error(message)
      }

      const payload = await response.json()
      if (!payload.success) {
        throw new Error('Gmail sync completed unsuccessfully.')
      }
    } catch (error) {
      setErrorMessage(error.message === 'Failed to fetch' ? 'Unable to reach Gmail sync. Showing your latest imported emails.' : (error.message || 'Gmail sync failed.'))
    } finally {
      await fetchEmails()
    }
  }

  useEffect(() => {
    if (!user) return

    const userKey = user.id || user.email
    if (autoSyncUserRef.current === userKey) return

    autoSyncUserRef.current = userKey
    handleSyncGmail()
  }, [user])

  const openReplyComposer = (email) => {
    setReplyEmail(email)
    setReplyBody('')
    setReplyTo(email.sender || '')
    setReplyCc('')
    setReplyBcc('')
    setReplySubject(email.subject || '')
    setShowCcBcc(false)
    setReplyAttachments([])
    setReplyError('')
    setIsDraggingAttachment(false)
  }

  const resetReplyComposer = useCallback(() => {
    setReplyEmail(null)
    setReplyBody('')
    setReplyTo('')
    setReplyCc('')
    setReplyBcc('')
    setReplySubject('')
    setShowCcBcc(false)
    setReplyAttachments([])
    setReplyError('')
  }, [])

  const hasReplyDraft = Boolean(
    getReplyPlainText(replyBody)
      || replyCc.trim()
      || replyBcc.trim()
      || replyAttachments.length
      || replySubject.trim() !== (replyEmail?.subject || '').trim()
      || replyTo.trim() !== (replyEmail?.sender || '').trim(),
  )

  const requestCloseComposer = useCallback(() => {
    if (sendingReply) return
    if (hasReplyDraft && !window.confirm('Discard this reply draft?')) return
    resetReplyComposer()
  }, [hasReplyDraft, resetReplyComposer, sendingReply])

  useEffect(() => {
    if (!replyEmail) return undefined

    const handleComposerKeyDown = (event) => {
      if (event.key === 'Escape') requestCloseComposer()
    }

    window.addEventListener('keydown', handleComposerKeyDown)
    replyEditorRef.current?.focus()
    return () => window.removeEventListener('keydown', handleComposerKeyDown)
  }, [replyEmail, hasReplyDraft, sendingReply, requestCloseComposer])

  const addAttachments = (fileList) => {
    const selectedFiles = Array.from(fileList || [])
    if (!selectedFiles.length) return

    const existingBytes = replyAttachments.reduce((total, item) => total + item.file.size, 0)
    if (replyAttachments.length + selectedFiles.length > MAX_REPLY_ATTACHMENTS) {
      setReplyError(`You can attach up to ${MAX_REPLY_ATTACHMENTS} files.`)
      return
    }

    const oversizedFile = selectedFiles.find((file) => file.size > MAX_REPLY_ATTACHMENT_BYTES)
    if (oversizedFile) {
      setReplyError(`${oversizedFile.name} exceeds the 10 MB attachment limit.`)
      return
    }

    const blockedFile = selectedFiles.find((file) => BLOCKED_REPLY_EXTENSIONS.has(`.${file.name.split('.').pop()?.toLowerCase()}`))
    if (blockedFile) {
      setReplyError(`${blockedFile.name} is not an allowed attachment type.`)
      return
    }

    const selectedBytes = selectedFiles.reduce((total, file) => total + file.size, 0)
    if (existingBytes + selectedBytes > MAX_REPLY_TOTAL_BYTES) {
      setReplyError('The combined attachment size cannot exceed 25 MB.')
      return
    }

    setReplyError('')
    setReplyAttachments((current) => [
      ...current,
      ...selectedFiles.map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`,
        file,
      })),
    ])
  }

  const handleAttachmentSelection = (event) => {
    addAttachments(event.target.files)
    event.target.value = ''
  }

  const handleAttachmentDrop = (event) => {
    event.preventDefault()
    setIsDraggingAttachment(false)
    if (!sendingReply) addAttachments(event.dataTransfer.files)
  }

  const removeAttachment = (attachmentId) => {
    setReplyAttachments((current) => current.filter((item) => item.id !== attachmentId))
  }

  const applyFormatting = (command) => {
    if (command === 'createLink') {
      const url = window.prompt('Enter a link URL')
      if (!url) return
      document.execCommand(command, false, url)
    } else {
      document.execCommand(command, false)
    }
    replyEditorRef.current?.focus()
  }

  const handleSendReply = async (event) => {
    event.preventDefault()
    if (!replyEmail || !getReplyPlainText(replyBody) || sendingReply) return

    if (!replyTo.trim() || !hasValidRecipients(replyTo)) {
      setReplyError('Enter at least one valid recipient email address.')
      return
    }

    try {
      setSendingReply(true)
      setReplyError('')
      const formData = new FormData()
      formData.append('body', replyBody)
      formData.append('to', replyTo.trim())
      formData.append('cc', replyCc.trim())
      formData.append('bcc', replyBcc.trim())
      formData.append('subject', replySubject.trim())
      replyAttachments.forEach(({ file }) => formData.append('attachments', file))

      const response = await fetch(`${API_BASE_URL}/api/emails/${replyEmail.id}/reply`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
      })
      const payload = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to send the reply.')
      }

      resetReplyComposer()
    } catch (error) {
      setReplyError(error.message || 'Unable to send the reply.')
    } finally {
      setSendingReply(false)
    }
  }

  if (loadingUser) {
    return (
      <main className="grid min-h-svh place-items-center bg-[#faf9f6] p-6">
        <div className="rounded-lg border border-[#deddd7] bg-[#fffefa] p-6 text-sm text-[#738078] shadow-sm">Checking your session…</div>
      </main>
    )
  }

  if (!user) {
    return (
      <main className="grid min-h-svh place-items-center bg-[#f6f5f0] px-4 py-6 text-[#202825] sm:px-6">
        <section className="w-full max-w-[27rem] rounded-xl border border-[#deddd7] bg-[#fffefa] px-5 py-7 shadow-[0_14px_32px_rgba(40,47,43,0.07)] sm:px-8 sm:py-9" aria-labelledby="auth-title">
          <div className="flex flex-col items-center text-center">
            <span className="grid h-11 w-11 place-items-center rounded-[8px] bg-[#176b61] text-[0.78rem] font-extrabold tracking-[0.02em] text-white">IS</span>
            <p className="mt-3 text-[0.95rem] font-semibold tracking-[-0.01em] text-[#26332e]">InboxSense</p>
            <h1 id="auth-title" className="mt-8 text-[clamp(1.8rem,7vw,2.35rem)] font-medium leading-[1.12] tracking-[-0.035em] text-[#202825]">Your inbox, understood.</h1>
            <p className="mt-3 max-w-[22rem] text-[0.9rem] leading-[1.55] text-[#707a75]">Connect your Gmail account to discover what your emails require from you.</p>
          </div>
          {errorMessage && <p className="mt-5 rounded-md border border-[#f0d4cd] bg-[#fff3ef] p-3 text-left text-sm text-[#9a4d3d]" role="alert">{errorMessage}</p>}
          {logoutError && <p className="mt-3 rounded-md border border-[#f0d4cd] bg-[#fff3ef] p-3 text-left text-sm text-[#9a4d3d]" role="alert">{logoutError}</p>}
          <button type="button" className="mt-7 flex min-h-12 w-full items-center justify-center gap-3 rounded-lg border border-[#c9c9c2] bg-[#176b61] px-4 py-3 text-[0.88rem] font-semibold text-white shadow-[0_5px_13px_rgba(23,107,97,0.14)] transition-colors hover:bg-[#0f806f] active:bg-[#0b574f] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#176b61] disabled:cursor-wait disabled:opacity-65" onClick={handleGoogleLogin}><GoogleLogo /> Continue with Google</button>
        </section>
      </main>
    )
  }

  return (
    <main className="grid h-svh min-h-0 grid-cols-[215px_minmax(0,1fr)] overflow-hidden bg-[#faf9f6] text-[#202825] max-[900px]:grid-cols-[64px_minmax(0,1fr)] max-[767px]:block">
      <aside className="flex min-h-svh flex-col gap-5 border-r border-[#deddd7] bg-[#fffefa] px-[0.4rem] pt-5 pb-4 text-[#44504b] max-[900px]:items-center max-[900px]:px-[0.4rem] max-[767px]:hidden">
        <div className="flex items-center gap-[0.6rem] px-[0.1rem] text-[#202825] max-[900px]:justify-center">
          <span className="grid h-[1.9rem] w-[1.9rem] shrink-0 place-items-center rounded-[7px] bg-[#176b61] text-[0.7rem] font-extrabold text-white">IS</span>
          <div>
            <p className="hidden">Workspace</p>
            <strong className="text-base font-medium max-[900px]:hidden">InboxSense</strong>
          </div>
        </div>

        <CategoryNavigation selectedCategory={selectedCategory} categoryCounts={categoryCounts} onSelect={setSelectedCategory} />
      </aside>

      <section className="flex min-h-0 min-w-0 flex-col overflow-hidden max-[767px]:h-svh max-[767px]:overflow-hidden">
        {loadingEmails ? (
          <EmailLoadingVisualization />
        ) : <>
        <header className="hidden min-h-14 flex-none items-center gap-2 border-0 bg-[#fffefa] px-[0.55rem] text-[#20332e] max-[767px]:flex">
          <label className="flex min-w-0 flex-1 items-center gap-[0.35rem] rounded-lg border border-[#d9d8d2] bg-[#f7f6f2] px-[0.65rem] py-2 text-[0.68rem] text-[#8c9590] focus-within:border-[#73a79b] focus-within:bg-[#fffefa] focus-within:ring-2 focus-within:ring-[#d3e8e0]"><span aria-hidden="true">⌕</span><input className="w-full min-w-0 flex-1 border-0 bg-transparent text-inherit outline-none placeholder:text-[#8c9590]" type="search" aria-label="Search mail" placeholder="Search mail" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /></label>
            <ProfileControl user={user} open={profileOpen} onToggle={() => setProfileOpen((current) => !current)} onLogout={handleLogout} loggingOut={loggingOut} selectedCategory={selectedCategory} categoryCounts={categoryCounts} onSelectCategory={(category) => { setSelectedCategory(category); setProfileOpen(false) }} />
        </header>
        <header className="flex h-[58px] flex-none items-center justify-between border-b border-[#deddd7] px-4 max-[767px]:hidden">
          <div className="flex items-baseline gap-[0.55rem]"><h2 className="text-base font-bold text-[#202825]">Inbox</h2></div>
          <div className="flex items-center gap-[0.7rem]">
            <label className="flex w-[220px] min-w-0 items-center gap-[0.35rem] rounded-lg border border-[#d9d8d2] bg-[#f7f6f2] px-[0.65rem] py-2 text-[0.68rem] text-[#8c9590] focus-within:border-[#73a79b] focus-within:bg-[#fffefa] focus-within:ring-2 focus-within:ring-[#d3e8e0]"><span aria-hidden="true">⌕</span><input className="w-full min-w-0 flex-1 border-0 bg-transparent text-inherit outline-none placeholder:text-[#8c9590]" type="search" aria-label="Search mail" placeholder="Search mail" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /><kbd className="text-[0.6rem] text-[#a1a8a3]">⌘ K</kbd></label>
            <ProfileControl user={user} open={profileOpen} onToggle={() => setProfileOpen((current) => !current)} onLogout={handleLogout} loggingOut={loggingOut} selectedCategory={selectedCategory} categoryCounts={categoryCounts} onSelectCategory={(category) => { setSelectedCategory(category); setProfileOpen(false) }} />
          </div>
        </header>

        {!loadingEmails && emails.length > 0 && <div className="flex-none border-t border-[#e5e7e1] px-4 pt-[0.7rem] pb-[0.6rem] max-[767px]:px-3 max-[767px]:pt-[0.6rem] max-[767px]:pb-[0.65rem]">
          <div className="flex justify-between text-[0.66rem] text-[#69746e] max-[767px]:text-[0.7rem]"><strong className="text-[#2c3631]">Inbox distribution</strong><span className="text-[#a0a8a3]">{emailCount} messages</span></div>
          <div className="mt-[0.45rem] flex h-[7px] gap-0.5 overflow-hidden rounded-[3px] max-[767px]:mt-[0.38rem] max-[767px]:h-[5px]">{CATEGORY_FILTERS.map((category) => <span key={category} className={`min-w-[5px] ${CATEGORY_STYLES[category].bar}`} style={{ width: `${Math.max(5, (categoryCounts[category] / Math.max(1, emailCount)) * 100)}%` }} />)}</div>
          <div className="mt-[0.45rem] flex flex-wrap gap-3 text-[0.62rem] text-[#7b8580] max-[767px]:mt-[0.45rem] max-[767px]:gap-x-[0.65rem] max-[767px]:gap-y-[0.3rem] max-[767px]:text-[0.62rem]">{CATEGORY_FILTERS.map((category) => <span className="inline-flex items-center gap-1" key={category}><i className={`h-[0.35rem] w-[0.35rem] rounded-full ${CATEGORY_STYLES[category].bar}`} />{CATEGORY_LABELS[category]} · {categoryCounts[category]}</span>)}</div>
        </div>}

        {errorMessage && <div className="mx-4 mt-3 rounded-md border border-[#f0d4cd] bg-[#fff3ef] p-3 text-sm text-[#9a4d3d]">{errorMessage}</div>}

        {errorMessage && emails.length === 0 ? (
          <div className="grid flex-1 place-items-center text-sm text-[#9a4d3d]">Unable to load emails. Please try again.</div>
        ) : emails.length === 0 ? (
          <div className="grid flex-1 place-items-center text-sm text-[#738078]">{searchQuery.trim() ? 'No emails found.' : `No emails found in ${CATEGORY_LABELS[selectedCategory] || selectedCategory}.`}</div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(360px,510px)_minmax(0,1fr)] overflow-hidden max-[900px]:grid-cols-[minmax(300px,1fr)] max-[767px]:grid-cols-1">
            <section className="mobile-email-list min-h-0 min-w-0 overflow-x-hidden overflow-y-auto max-[767px]:w-full max-[767px]:[scrollbar-width:none] max-[767px]:[&::-webkit-scrollbar]:hidden" aria-label="Inbox messages">
              <div className="flex justify-between px-4 py-[0.55rem] text-[0.68rem] text-[#7f8984] max-[767px]:px-3 max-[767px]:py-[0.48rem]"><span>☑ &nbsp; ↻ &nbsp; ▽</span><span>1–{Math.min(6, visibleEmails.length)} of {emailCount}</span></div>
              {visibleEmails.length === 0 ? <div className="grid min-h-40 place-items-center text-sm text-[#738078]">{searchQuery.trim() ? 'No emails found.' : `No emails in ${selectedCategory}.`}</div> : visibleEmails.map((email) => <EmailCard key={email.gmail_message_id} email={email} onReply={openReplyComposer} expanded={isMobile && expandedEmailId === email.gmail_message_id} selected={!isMobile && email === activeEmail} onOpen={(emailToOpen) => {
                if (isMobile) {
                  setExpandedEmailId((current) => current === emailToOpen.gmail_message_id ? null : emailToOpen.gmail_message_id)
                } else {
                  setSelectedEmail(emailToOpen)
                }
              }} />)}
            </section>
            {!isMobile && <EmailDetailPanel email={activeEmail} onReply={openReplyComposer} />}
          </div>
        )}

        {replyEmail && (
          <div className="fixed inset-0 z-20 grid place-items-center bg-[rgba(28,38,34,0.38)] p-5 max-[560px]:items-stretch max-[560px]:p-0" role="presentation">
            <section
              className={`max-h-[min(760px,calc(100vh-2rem))] w-full max-w-[680px] overflow-y-auto rounded-xl border border-[#d8d7d0] bg-[#fffefa] p-5 text-[#202825] shadow-[0_18px_45px_rgba(24,35,30,0.2)] max-[560px]:h-dvh max-[560px]:max-h-dvh max-[560px]:min-h-dvh max-[560px]:rounded-none max-[560px]:border-0 max-[560px]:p-4 ${isDraggingAttachment ? 'border-[#176b61] shadow-[0_0_0_3px_#d8ebe6,0_18px_45px_rgba(24,35,30,0.2)]' : ''}`}
              role="dialog"
              aria-modal="true"
              aria-labelledby="reply-title"
              onDragOver={(event) => {
                event.preventDefault()
                if (!sendingReply) setIsDraggingAttachment(true)
              }}
              onDragLeave={() => setIsDraggingAttachment(false)}
              onDrop={handleAttachmentDrop}
            >
              <div className="flex items-start justify-between gap-4 border-b border-[#deddd7] pb-[0.9rem]">
                <div>
                  <p className="mb-[0.35rem] text-[0.64rem] text-[#176b61]">Reply in thread</p>
                  <h3 id="reply-title" className="text-base font-semibold leading-[1.35] text-[#202825]">{replyEmail.subject || '(No subject)'}</h3>
                </div>
                <button type="button" className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-[#deddd7] bg-[#fffefa] text-xl leading-none text-[#68736d] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:cursor-wait disabled:opacity-60" onClick={requestCloseComposer} disabled={sendingReply} aria-label="Close reply composer">
                  ×
                </button>
              </div>

              {replyError && <div className="mt-3 rounded-md border border-[#f0d4cd] bg-[#fff3ef] p-3 text-sm text-[#9a4d3d]">{replyError}</div>}

              <form onSubmit={handleSendReply}>
                <div className="mt-3 grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-[0.65rem] max-[560px]:grid-cols-[3.6rem_minmax(0,1fr)]">
                  <label className="text-xs font-semibold text-[#68736d]" htmlFor="reply-to">To</label>
                  <input className="w-full min-w-0 rounded-md border border-[#d8d7d0] bg-white px-[0.65rem] py-[0.58rem] text-[0.78rem] text-[#202825] focus:border-[#73a79b] focus:outline-2 focus:outline-offset-1 focus:outline-[rgba(23,107,97,0.16)]" id="reply-to" type="text" value={replyTo} onChange={(event) => setReplyTo(event.target.value)} disabled={sendingReply} aria-required="true" placeholder="recipient@example.com" />
                  <button type="button" className={`whitespace-nowrap rounded-md bg-transparent px-2 py-1 text-[0.7rem] font-semibold text-[#176b61] transition-colors hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60 max-[560px]:col-start-2 max-[560px]:justify-self-start ${showCcBcc ? 'bg-[#c8e4da] text-[#174f47]' : ''}`} onClick={() => setShowCcBcc((visible) => !visible)} disabled={sendingReply}>
                    {showCcBcc ? 'Hide Cc/Bcc' : 'Cc / Bcc'}
                  </button>
                </div>
                {showCcBcc && (
                  <div className="mb-0 ml-[4.5rem] border-l-2 border-[#d8ebe6] pl-[0.65rem] max-[560px]:ml-[3.6rem]">
                    <div className="mt-3 grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-[0.65rem] max-[560px]:grid-cols-[3.6rem_minmax(0,1fr)]">
                      <label className="text-xs font-semibold text-[#68736d]" htmlFor="reply-cc">Cc</label>
                      <input className="w-full min-w-0 rounded-md border border-[#d8d7d0] bg-white px-[0.65rem] py-[0.58rem] text-[0.78rem] text-[#202825] focus:border-[#73a79b] focus:outline-2 focus:outline-offset-1 focus:outline-[rgba(23,107,97,0.16)]" id="reply-cc" type="text" value={replyCc} onChange={(event) => setReplyCc(event.target.value)} disabled={sendingReply} placeholder="Optional recipients" />
                    </div>
                    <div className="mt-3 grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-[0.65rem] max-[560px]:grid-cols-[3.6rem_minmax(0,1fr)]">
                      <label className="text-xs font-semibold text-[#68736d]" htmlFor="reply-bcc">Bcc</label>
                      <input className="w-full min-w-0 rounded-md border border-[#d8d7d0] bg-white px-[0.65rem] py-[0.58rem] text-[0.78rem] text-[#202825] focus:border-[#73a79b] focus:outline-2 focus:outline-offset-1 focus:outline-[rgba(23,107,97,0.16)]" id="reply-bcc" type="text" value={replyBcc} onChange={(event) => setReplyBcc(event.target.value)} disabled={sendingReply} placeholder="Optional recipients" />
                    </div>
                  </div>
                )}
                <div className="mt-3 grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-[0.65rem] max-[560px]:grid-cols-[3.6rem_minmax(0,1fr)]">
                  <label className="text-xs font-semibold text-[#68736d]" htmlFor="reply-subject">Subject</label>
                  <input className="w-full min-w-0 rounded-md border border-[#d8d7d0] bg-white px-[0.65rem] py-[0.58rem] text-[0.78rem] text-[#202825] focus:border-[#73a79b] focus:outline-2 focus:outline-offset-1 focus:outline-[rgba(23,107,97,0.16)]" id="reply-subject" type="text" value={replySubject} onChange={(event) => setReplySubject(event.target.value)} disabled={sendingReply} />
                </div>
                <div className="my-[0.9rem] flex items-baseline gap-[0.45rem] text-[0.72rem] text-[#929b96]">
                  <span>Replying in thread</span>
                  <strong className="font-semibold text-[#46534d]">{replyEmail.sender || 'Unknown sender'}</strong>
                </div>
                <input
                  ref={attachmentInputRef}
                  className="hidden"
                  type="file"
                  multiple
                  onChange={handleAttachmentSelection}
                  disabled={sendingReply}
                />
                <div className="mt-[0.9rem] flex flex-wrap items-center gap-[0.3rem]" aria-label="Message formatting">
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('bold')} disabled={sendingReply} title="Bold">
                    <strong>B</strong>
                  </button>
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('italic')} disabled={sendingReply} title="Italic">
                    <em>I</em>
                  </button>
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('underline')} disabled={sendingReply} title="Underline">
                    <u>U</u>
                  </button>
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('insertUnorderedList')} disabled={sendingReply} title="Bullet list">
                    • List
                  </button>
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('insertOrderedList')} disabled={sendingReply} title="Numbered list">
                    1. List
                  </button>
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('createLink')} disabled={sendingReply} title="Insert link">
                    Link
                  </button>
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('justifyLeft')} disabled={sendingReply} title="Align left">
                    Left
                  </button>
                  <button className="min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60" type="button" onClick={() => applyFormatting('justifyCenter')} disabled={sendingReply} title="Align center">
                    Center
                  </button>
                  <button type="button" className="ml-auto min-h-8 rounded-[5px] border border-[#deddd7] bg-[#f7f6f2] px-2 text-[0.7rem] text-[#56625c] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:opacity-60 max-[560px]:ml-0" onClick={() => attachmentInputRef.current?.click()} disabled={sendingReply} title="Attach files">
                    Attach files
                  </button>
                </div>
                <div
                  ref={replyEditorRef}
                  className="mt-[0.65rem] block min-h-[175px] w-full rounded-md border border-[#d8d7d0] bg-white p-3 text-[0.82rem] leading-[1.6] text-[#202825] focus:border-[#73a79b] focus:outline-2 focus:outline-offset-1 focus:outline-[rgba(23,107,97,0.16)] empty:before:content-[attr(data-placeholder)] empty:before:text-[#a1a9a4]"
                  contentEditable={!sendingReply}
                  role="textbox"
                  aria-multiline="true"
                  aria-label="Reply message"
                  data-placeholder="Write your reply…"
                  onInput={(event) => setReplyBody(event.currentTarget.innerHTML)}
                  suppressContentEditableWarning
                />
                {replyAttachments.length > 0 && (
                  <div className="mt-[0.65rem] flex flex-wrap gap-[0.45rem]" aria-label="Selected attachments">
                    {replyAttachments.map(({ id, file }) => (
                      <div className="inline-flex max-w-full items-center gap-[0.45rem] rounded-md border border-[#d8d7d0] bg-[#f7f6f2] px-[0.55rem] py-[0.4rem] text-[0.7rem] text-[#46534d]" key={id}>
                        <span className="max-w-[210px] overflow-hidden text-ellipsis whitespace-nowrap">{file.name}</span>
                        <small className="text-[#929b96]">{formatFileSize(file.size)}</small>
                        <button className="rounded px-1 text-[#78847e] transition-colors hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-[#176b61]" type="button" onClick={() => removeAttachment(id)} disabled={sendingReply} aria-label={`Remove ${file.name}`}>
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-4 flex justify-end gap-[0.6rem] max-[560px]:sticky max-[560px]:bottom-[-1rem] max-[560px]:z-[1] max-[560px]:border-t max-[560px]:border-[#deddd7] max-[560px]:bg-[#fffefa] max-[560px]:px-0 max-[560px]:pt-3 max-[560px]:pb-4 max-[560px]:[&_button]:flex-1">
                  <button type="button" className="h-[2.45rem] rounded-md border border-[#d8d7d0] bg-[#fffefa] px-4 text-[0.76rem] text-[#5e6a64] transition-colors hover:border-[#73a79b] hover:bg-[#c8e4da] hover:text-[#174f47] active:bg-[#afd7c8] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#176b61] disabled:cursor-wait disabled:opacity-60" onClick={requestCloseComposer} disabled={sendingReply}>
                    Cancel
                  </button>
                  <button type="submit" className="h-[2.45rem] rounded-md border border-[#176b61] bg-[#176b61] px-4 text-[0.76rem] text-white transition-colors hover:bg-[#0f806f] active:bg-[#0b574f] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#176b61] disabled:cursor-wait disabled:opacity-60" disabled={sendingReply || !getReplyPlainText(replyBody)}>
                    {sendingReply ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </form>
            </section>
          </div>
        )}
        </>}
      </section>
    </main>
  )
}

export default App
