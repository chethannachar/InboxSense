function GoogleLogo() {
  return (
    <svg className="h-6 w-6" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M21.35 12.27c0-.79-.07-1.55-.2-2.27H12v4.3h5.24a4.48 4.48 0 0 1-1.94 2.94v2.45h3.14c1.84-1.69 2.91-4.18 2.91-7.42Z" />
      <path fill="#34A853" d="M12 21.5c2.63 0 4.84-.87 6.45-2.36l-3.14-2.45c-.87.58-1.98.92-3.31.92-2.54 0-4.7-1.72-5.47-4.03H3.28v2.53A9.74 9.74 0 0 0 12 21.5Z" />
      <path fill="#FBBC05" d="M6.53 13.58a5.86 5.86 0 0 1 0-3.16V7.89H3.28a9.5 9.5 0 0 0 0 8.22l3.25-2.53Z" />
      <path fill="#EA4335" d="M12 6.39c1.43 0 2.71.49 3.72 1.46l2.79-2.79C16.84 3.5 14.63 2.5 12 2.5a9.74 9.74 0 0 0-8.72 5.39l3.25 2.53C7.3 8.11 9.46 6.39 12 6.39Z" />
    </svg>
  )
}

const CATEGORY_DESCRIPTIONS = {
  ACTION_REQUIRED: 'Needs a response',
  OPPORTUNITIES: 'Worth exploring',
  EVENTS: 'Dates to remember',
  ALERTS: 'Time-sensitive',
  INFORMATION: 'Useful context',
}

export default function AuthScreen({ onGoogleLogin, errorMessage, logoutError, categories, categoryLabels, categoryStyles }) {
  return (
    <main className="auth-page grid h-svh min-h-0 grid-rows-[minmax(0,0.4fr)_minmax(0,0.6fr)] max-[639px]:grid-rows-[minmax(0,0.34fr)_minmax(0,0.66fr)] overflow-hidden bg-[#f6f5f0] text-[#202825] lg:grid-rows-1 lg:grid-cols-[minmax(0,1.25fr)_minmax(25rem,0.75fr)]">
      <section className="relative isolate hidden min-h-0 flex-col overflow-hidden bg-[#163f38] px-6 pb-7 pt-6 text-[#f7f7ee] sm:px-10 sm:pb-9 sm:pt-8 lg:flex lg:h-svh lg:px-[clamp(2.5rem,6vw,6rem)] lg:pb-10 lg:pt-9" aria-labelledby="brand-title">
        <div className="auth-grid-texture pointer-events-none absolute inset-0 -z-10" aria-hidden="true" />
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-[8px] bg-[#f2b66d] text-[0.72rem] font-extrabold text-[#263c35]" aria-hidden="true">IS</span>
            <strong className="text-[1rem] font-medium">InboxSense</strong>
          </div>
          <span className="hidden text-[0.62rem] font-semibold text-[#bdd0c8] sm:block">A CLEARER VIEW OF YOUR INBOX</span>
        </header>

        <div className="relative z-10 mt-12 grid flex-1 content-start sm:mt-16 xl:mt-[clamp(3rem,9vh,7rem)] xl:grid-cols-[minmax(0,1.1fr)_minmax(19rem,0.9fr)] xl:items-center xl:gap-8">
          <div className="max-w-[37rem]">
            <p className="mb-4 text-[0.66rem] font-bold text-[#f2b66d]">INBOX INTELLIGENCE, IN CONTEXT</p>
            <h1 id="brand-title" className="max-w-[35rem] text-[2.65rem] font-medium leading-[1.02] text-[#f7f7ee] sm:text-[3.5rem] lg:text-[clamp(2.75rem,3.4vw,4.5rem)]">Know what your inbox asks of you.</h1>
            <p className="mt-5 max-w-[29rem] text-[0.92rem] leading-[1.7] text-[#c1d1cb] sm:text-[1rem]">The important things rise to the surface. See actions, opportunities, and dates worth your attention at a glance.</p>
            <ul className="mt-7 grid max-w-[34rem] grid-cols-3 border-y border-white/15 py-4" aria-label="InboxSense classification system">
              {categories.map((category, index) => (
                <li className={`min-w-0 px-2 first:pl-0 ${index % 3 !== 2 && index < categories.length - 1 ? 'border-r border-white/15' : ''}`} key={category}>
                  <span className={`mb-2 block h-[3px] w-5 rounded-full ${categoryStyles[category].bar}`} aria-hidden="true" />
                  <span className="block text-[0.58rem] font-semibold leading-[1.25] text-[#f7f7ee] sm:text-[0.66rem]">{categoryLabels[category]}</span>
                  <span className="mt-1 hidden text-[0.6rem] leading-[1.35] text-[#a9c0b7] sm:block">{CATEGORY_DESCRIPTIONS[category]}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="auth-artwork relative mx-auto mt-10 hidden h-[17rem] w-full max-w-[34rem] sm:mt-14 sm:h-[22rem] xl:mt-0 xl:h-[min(56vh,34rem)] xl:min-h-[25rem] xl:block" role="img" aria-label="InboxSense organizing incoming messages by what matters">
            <div className="absolute inset-x-[7%] bottom-[5%] top-[8%] rotate-[-5deg] rounded-[1.4rem] border border-white/10 bg-[#28584d]/60" />
            <div className="absolute inset-x-[4%] bottom-[2%] top-[4%] rotate-[3deg] rounded-[1.4rem] border border-white/15 bg-[#204c43]" />
            <div className="auth-inbox-panel absolute inset-0 overflow-hidden rounded-[1.25rem] border border-[#d6e2d9]/70 bg-[#f7f6f0] text-[#263a34] shadow-[0_26px_70px_rgba(4,23,20,0.3)]">
              <div className="flex items-center justify-between border-b border-[#e5e6df] px-4 py-3 sm:px-6 sm:py-4">
                <div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-md bg-[#dcebe4] text-[#176b61]"><svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M3.5 6.5h17v12h-17z" /><path d="m4 7 8 6 8-6" /></svg></span><span className="text-[0.69rem] font-semibold sm:text-[0.76rem]">Priority inbox</span></div>
                <span className="flex items-center gap-1.5 text-[0.58rem] font-medium text-[#718079] sm:text-[0.66rem]"><span className="auth-live-dot h-1.5 w-1.5 rounded-full bg-[#51a879]" /> LIVE SORTING</span>
              </div>
              <div className="px-3 py-2 sm:px-5 sm:py-3">
                <div className="mb-2 flex items-center justify-between px-2 text-[0.55rem] font-semibold text-[#9aa39d] sm:px-3 sm:text-[0.62rem]"><span>MESSAGE</span><span>WHY IT MATTERS</span></div>
                <div className="flex min-w-0 items-center gap-2.5 rounded-lg border border-[#e8e8e1] bg-white px-2.5 py-2.5 sm:gap-3 sm:px-3 sm:py-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#f8e5ca] text-[0.63rem] font-bold text-[#9a6227] sm:h-9 sm:w-9">M</span>
                  <div className="min-w-0 flex-1"><p className="truncate text-[0.62rem] font-semibold sm:text-[0.7rem]">Maya Chen <span className="ml-1 font-normal text-[#9aa39d]">· 9:42 AM</span></p><p className="mt-1 truncate text-[0.58rem] text-[#627169] sm:text-[0.64rem]">Final review needed by Friday</p></div>
                  <span className="shrink-0 rounded bg-[#fff0dc] px-1.5 py-1 text-[0.52rem] font-semibold text-[#a56721] sm:px-2 sm:text-[0.58rem]">ACTION</span>
                </div>
                <div className="mt-2 flex min-w-0 items-center gap-2.5 rounded-lg border border-[#e8e8e1] bg-white px-2.5 py-2.5 sm:gap-3 sm:px-3 sm:py-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#e3efe2] text-[0.63rem] font-bold text-[#4c7b59] sm:h-9 sm:w-9">J</span>
                  <div className="min-w-0 flex-1"><p className="truncate text-[0.62rem] font-semibold sm:text-[0.7rem]">Jordan Lee <span className="ml-1 font-normal text-[#9aa39d]">· 9:18 AM</span></p><p className="mt-1 truncate text-[0.58rem] text-[#627169] sm:text-[0.64rem]">A new role that fits your interests</p></div>
                  <span className="shrink-0 rounded bg-[#e7f2e8] px-1.5 py-1 text-[0.52rem] font-semibold text-[#4f8060] sm:px-2 sm:text-[0.58rem]">OPPORTUNITY</span>
                </div>
                <div className="mt-2 flex min-w-0 items-center gap-2.5 rounded-lg border border-[#e8e8e1] bg-white px-2.5 py-2.5 sm:gap-3 sm:px-3 sm:py-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#e6eef7] text-[0.63rem] font-bold text-[#55789b] sm:h-9 sm:w-9">C</span>
                  <div className="min-w-0 flex-1"><p className="truncate text-[0.62rem] font-semibold sm:text-[0.7rem]">Calendar desk <span className="ml-1 font-normal text-[#9aa39d]">· 8:56 AM</span></p><p className="mt-1 truncate text-[0.58rem] text-[#627169] sm:text-[0.64rem]">Design sync, Wednesday at 2:00</p></div>
                  <span className="shrink-0 rounded bg-[#e6eef7] px-1.5 py-1 text-[0.52rem] font-semibold text-[#55789b] sm:px-2 sm:text-[0.58rem]">EVENT</span>
                </div>
                <div className="mx-2 mt-3 flex items-center justify-between rounded-lg bg-[#e7f1ed] px-3 py-2 sm:mx-3 sm:mt-4 sm:px-4 sm:py-2.5">
                  <span className="text-[0.58rem] font-medium text-[#45645a] sm:text-[0.65rem]">Your day, in focus</span>
                  <span className="text-[0.58rem] font-semibold text-[#176b61] sm:text-[0.65rem]">3 things to see <span aria-hidden="true">→</span></span>
                </div>
              </div>
            </div>
            <div className="auth-float-note absolute -right-1 top-[12%] z-10 flex items-center gap-2 rounded-lg border border-[#f1e0c9] bg-[#fff9ee] px-3 py-2 text-[0.6rem] font-semibold text-[#805d34] shadow-lg sm:-right-4 sm:px-4 sm:py-2.5 sm:text-[0.66rem]"><span className="grid h-6 w-6 place-items-center rounded-full bg-[#f5e2c6] text-[#a56d2f]">✦</span>Only the useful stuff</div>
            <div className="auth-float-note auth-float-note-delay absolute -bottom-2 left-0 z-10 flex items-center gap-2 rounded-lg border border-[#d3e4da] bg-[#f3faf5] px-3 py-2 text-[0.6rem] font-semibold text-[#426b53] shadow-lg sm:-left-5 sm:px-4 sm:py-2.5 sm:text-[0.66rem]"><span className="grid h-6 w-6 place-items-center rounded-full bg-[#dcecdf] text-[#4f8060]">✓</span>Sorted by what matters</div>
          </div>
        </div>

        <footer className="relative z-10 mt-10 flex items-center justify-between border-t border-white/15 pt-4 text-[0.62rem] text-[#a9c0b7] sm:mt-12 sm:pt-5">
          <span>© 2026 InboxSense</span>
          <span>Your attention, thoughtfully organized.</span>
        </footer>
      </section>

      <section className="relative isolate flex min-h-0 flex-col justify-center overflow-hidden bg-[#163f38] px-6 py-5 text-[#f7f7ee] max-[639px]:-translate-y-2 max-[639px]:px-5 max-[639px]:pt-3 max-[639px]:pb-2 lg:hidden sm:px-10" aria-label="InboxSense inbox preview">
        <div className="auth-grid-texture pointer-events-none absolute inset-0 -z-10" aria-hidden="true" />
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-[8px] bg-[#e2efe8] text-[0.72rem] font-extrabold text-[#176b61] max-[639px]:h-11 max-[639px]:w-11" aria-hidden="true">IS</span>
            <div>
              <strong className="text-[1rem] font-medium max-[639px]:text-[1.1rem]">InboxSense</strong>
              <span className="mt-0.5 block text-[0.58rem] font-semibold text-[#bdd0c8]">INBOX INTELLIGENCE</span>
            </div>
          </div>
          <div className="mt-3 rounded-[8px] border border-[#d6e2d9]/70 bg-[#f7f6f0] p-2.5 text-[#263a34] shadow-[0_10px_24px_rgba(4,23,20,0.18)] max-[639px]:mt-2 max-[639px]:p-2">
            <div className="mb-2 flex items-center justify-between px-0.5">
              <div className="flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-[6px] bg-[#dcebe4] text-[#176b61]" aria-hidden="true"><svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3.5 6.5h17v12h-17z" /><path d="m4 7 8 6 8-6" /></svg></span>
                <span className="text-[0.7rem] font-semibold">Priority inbox</span>
              </div>
              <span className="text-[0.52rem] font-semibold text-[#718079]">2 OF 3 PRIORITIES</span>
            </div>
            <div className="grid gap-1.5">
              <div className="flex min-w-0 items-center gap-2 rounded-[6px] border border-[#e8e8e1] bg-white px-2 py-1.5 max-[639px]:py-1">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#f8e5ca] text-[0.56rem] font-bold text-[#9a6227] max-[639px]:h-6 max-[639px]:w-6" aria-hidden="true">M</span>
                <div className="min-w-0 flex-1"><p className="truncate text-[0.62rem] font-semibold">Maya Chen</p><p className="truncate text-[0.54rem] text-[#627169]">Review due Friday</p></div>
                <span className="shrink-0 rounded-[4px] bg-[#fff0dc] px-1.5 py-1 text-[0.46rem] font-semibold text-[#a56721]">ACTION</span>
              </div>
              <div className="flex min-w-0 items-center gap-2 rounded-[6px] border border-[#e8e8e1] bg-white px-2 py-1.5 max-[639px]:py-1">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#e3efe2] text-[0.56rem] font-bold text-[#4c7b59] max-[639px]:h-6 max-[639px]:w-6" aria-hidden="true">J</span>
                <div className="min-w-0 flex-1"><p className="truncate text-[0.62rem] font-semibold">Jordan Lee</p><p className="truncate text-[0.54rem] text-[#627169]">A new role worth a look</p></div>
                <span className="shrink-0 rounded-[4px] bg-[#e7f2e8] px-1.5 py-1 text-[0.46rem] font-semibold text-[#4f8060]">OPPORTUNITY</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="flex h-full min-h-0 flex-col justify-center overflow-hidden bg-[#f6f5f0] px-6 py-3 sm:px-12 sm:py-4 lg:h-svh lg:px-[clamp(2.5rem,5vw,5.5rem)] lg:py-8" aria-labelledby="auth-title">
        <div className="mx-auto w-full max-w-[27rem]">
          <div className="mb-7 hidden items-center gap-2 text-[0.67rem] font-semibold text-[#61756b] sm:mb-10 lg:flex"><span className="h-px w-7 bg-[#e0a45d]" /> YOUR INBOX, WITH CLARITY</div>
          <p className="text-[0.67rem] font-bold text-[#176b61]">WELCOME TO INBOXSENSE</p>
          <h2 id="auth-title" className="mt-3 text-[1.85rem] font-medium leading-[1.06] text-[#202825] max-[639px]:mt-2 sm:text-[2.05rem] lg:mt-4 lg:text-[2.35rem] xl:text-[2.8rem]">A little less noise. A lot more signal.</h2>
          <p className="mt-5 max-w-[25rem] text-[0.94rem] leading-[1.7] text-[#68756e] max-[639px]:mt-3">InboxSense is an email dashboard that connects with your Google account to organize and categorize Gmail messages. Review relevant email details and reply from one focused view.</p>

          {errorMessage && <p className="mt-6 rounded-md border border-[#f0d4cd] bg-[#fff3ef] p-3 text-left text-sm text-[#9a4d3d]" role="alert">{errorMessage}</p>}
          {logoutError && <p className="mt-3 rounded-md border border-[#f0d4cd] bg-[#fff3ef] p-3 text-left text-sm text-[#9a4d3d]" role="alert">{logoutError}</p>}

          <button type="button" className="mt-8 flex min-h-[3.4rem] w-full items-center justify-center gap-3 rounded-[7px] border border-[#145b51] bg-[#176b61] px-4 py-3 text-[0.88rem] font-semibold text-white transition-[background-color,border-color,box-shadow,transform] duration-150 hover:border-[#104f47] hover:bg-[#12584f] hover:shadow-[0_3px_10px_rgba(40,47,43,0.16)] active:translate-y-px active:bg-[#104f47] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#176b61] motion-reduce:transition-none max-[639px]:mt-5" onClick={onGoogleLogin}>
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white" aria-hidden="true"><GoogleLogo /></span>
            <span className="text-center">Continue with Google</span>
          </button>

          <div className="mt-5 flex items-center gap-3 max-[639px]:mt-3">
            <span className="h-px flex-1 bg-[#e1e1da]" aria-hidden="true" />
            <p className="text-[0.68rem] text-[#7b8780]">Secure authentication powered by Google.</p>
            <span className="h-px flex-1 bg-[#e1e1da]" aria-hidden="true" />
          </div>
          <nav className="mt-7 flex flex-wrap gap-x-5 gap-y-2 text-[0.76rem] text-[#55716a] max-[639px]:mt-5" aria-label="Legal information">
            <a className="underline decoration-[#b9c9c0] underline-offset-4 hover:text-[#174f47] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#176b61]" href="/privacy?from=auth">Privacy Policy</a>
            <a className="underline decoration-[#b9c9c0] underline-offset-4 hover:text-[#174f47] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#176b61]" href="/terms?from=auth">Terms of Service</a>
          </nav>
          <div className="mt-12 hidden items-start gap-3 border-t border-[#deddd7] pt-5 text-[0.72rem] leading-[1.55] text-[#89938d] lg:flex"><span className="mt-0.5 text-[#176b61]" aria-hidden="true">◎</span><p>Your messages stay yours. InboxSense organizes your inbox so you can decide what deserves your attention.</p></div>
        </div>
      </section>
    </main>
  )
}