import { useEffect } from 'react'

const LEGAL_CONTENT = {
  privacy: {
    title: 'Privacy Policy',
    documentTitle: 'InboxSense Privacy Policy',
    updated: 'September 29, 2026',
    sections: [
      {
        heading: 'About InboxSense',
        paragraphs: [
          'InboxSense is an email dashboard that helps users organize and review Gmail messages. This policy describes information handled when you use InboxSense.',
        ],
      },
      {
        heading: 'Information we may receive',
        paragraphs: [
          'When you choose to sign in with Google, InboxSense may receive basic Google account information, such as your name and email address, along with authentication and session information needed to provide the service.',
          'If you authorize Gmail access, InboxSense may access Gmail message information permitted by the authorization you grant. The information available depends on the permissions presented to you and approved in your Google account.',
        ],
      },
      {
        heading: 'How email information is used',
        paragraphs: [
          'Gmail information is used to provide the features you request, such as synchronizing messages, displaying relevant email details, organizing or categorizing messages, and supporting email actions such as replying where available. InboxSense does not use Gmail content for unrelated purposes.',
        ],
      },
      {
        heading: 'Authentication and sessions',
        paragraphs: [
          'Authentication is initiated through Google OAuth. InboxSense uses session information to recognize an authenticated user and make requested features available. Browser requests to the service may include session credentials. You can end your session using the sign-out control in the application; you can also review or revoke InboxSense access from your Google Account settings.',
        ],
      },
      {
        heading: 'Sharing and disclosure',
        paragraphs: [
          'InboxSense does not sell users’ personal information. Information may be sent to Google when needed for Google sign-in or Gmail features you authorize. Information may also be processed by service providers that help operate InboxSense, if applicable, or disclosed when required by law or necessary to protect the service and its users. It is not shared for third-party advertising.',
        ],
      },
      {
        heading: 'Security',
        paragraphs: [
          'Reasonable administrative and technical measures are used to help protect information handled by InboxSense. No method of transmission or storage can be represented as completely secure, and no specific security certification is claimed.',
        ],
      },
      {
        heading: 'Retention and deletion',
        paragraphs: [
          'Information is kept only as needed to provide and maintain the service or address legitimate operational needs. The applicable retention period may depend on the information and how the service is used. Revoking Google access prevents future authorized access but may not remove information already held by InboxSense. To ask about access, correction, or deletion of information, contact the developer using the contact placeholder below.',
        ],
      },
      {
        heading: 'Your choices and rights',
        paragraphs: [
          'You can choose whether to sign in, manage or revoke connected-app permissions through Google, and request access to, correction of, or deletion of information associated with your use of InboxSense. Some features may not work without the permissions they need.',
        ],
      },
      {
        heading: 'Changes and contact',
        paragraphs: [
          'This policy may be updated as InboxSense changes. The updated version will be published on this page with a revised date.',
          'Privacy questions or requests: [Replace with a privacy contact email before publication].',
        ],
      },
    ],
  },
  terms: {
    title: 'Terms of Service',
    documentTitle: 'InboxSense Terms of Service',
    updated: 'September 29, 2026',
    sections: [
      {
        heading: 'Acceptance of these terms',
        paragraphs: [
          'By accessing or using InboxSense, you agree to these Terms of Service. If you do not agree, do not use the service.',
        ],
      },
      {
        heading: 'The service',
        paragraphs: [
          'InboxSense is an email dashboard that can connect to a Google account, organize and categorize Gmail messages, display relevant email information, and provide email actions such as replying where available. Features may change over time.',
        ],
      },
      {
        heading: 'Google account authorization',
        paragraphs: [
          'You choose whether to connect a Google account and are responsible for reviewing the permissions requested during Google authorization. Your use of Google services remains subject to Google’s applicable terms and policies. You may revoke InboxSense access through your Google Account settings; features requiring that access will then stop working.',
        ],
      },
      {
        heading: 'Your responsibilities and acceptable use',
        paragraphs: [
          'You are responsible for your account, the actions taken through it, and ensuring you have the rights and permissions needed to use connected accounts and information.',
        ],
        bullets: [
          'Use InboxSense only in compliance with applicable laws and the terms that apply to your connected accounts.',
          'Do not misuse, disrupt, probe, or attempt unauthorized access to InboxSense or its systems.',
          'Do not use the service to send unlawful, deceptive, or abusive communications.',
          'Keep your Google account credentials private and notify the appropriate service contact if you believe your account or session has been misused.',
        ],
      },
      {
        heading: 'Intellectual property',
        paragraphs: [
          'InboxSense and its associated software and branding are protected by applicable intellectual property laws. These terms do not transfer ownership to you. You retain your rights to your own content and email.',
        ],
      },
      {
        heading: 'Availability and changes',
        paragraphs: [
          'InboxSense is provided on an as-available basis. Features may be unavailable, changed, or discontinued, including due to maintenance, technical conditions, or changes to connected services. No uninterrupted availability is promised.',
        ],
      },
      {
        heading: 'Suspension or termination',
        paragraphs: [
          'You may stop using InboxSense and revoke its Google access at any time. Access may be suspended or ended if needed to protect the service or users, address misuse, comply with law, or discontinue the service.',
        ],
      },
      {
        heading: 'Limitation of liability',
        paragraphs: [
          'To the extent permitted by applicable law, InboxSense is not responsible for indirect, incidental, special, consequential, or punitive damages, or for loss of data, arising from or related to your use of the service. Nothing in these terms excludes liability that cannot lawfully be excluded.',
        ],
      },
      {
        heading: 'Changes to these terms',
        paragraphs: [
          'These terms may be updated as InboxSense changes. Updates will be posted on this page with a revised date. Continued use after updated terms are posted means you accept them, to the extent permitted by applicable law.',
        ],
      },
      {
        heading: 'Contact',
        paragraphs: [
          'Questions about these terms: [Replace with a contact email before publication].',
        ],
      },
    ],
  },
}

export default function LegalPage({ page }) {
  const content = LEGAL_CONTENT[page]

  useEffect(() => {
    document.title = content.documentTitle
    const description = document.querySelector('meta[name="description"]')
    if (description) {
      description.content = page === 'privacy'
        ? 'Learn how InboxSense handles account information, Gmail data, privacy choices, and deletion requests.'
        : 'Review the terms for using InboxSense, an email dashboard for organizing and reviewing Gmail messages.'
    }
  }, [content.documentTitle, page])

  return (
    <main className="min-h-svh bg-[#f6f5f0] px-5 py-8 text-[#202825] sm:px-8 sm:py-12">
      <div className="mx-auto max-w-[50rem]">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#d9ded8] pb-5">
          <a className="flex items-center gap-2.5 text-[#20332e] no-underline" href="/" aria-label="InboxSense home">
            <span className="grid h-9 w-9 place-items-center rounded-[7px] bg-[#176b61] text-[0.68rem] font-extrabold text-white" aria-hidden="true">IS</span>
            <span className="text-[0.96rem] font-semibold">InboxSense</span>
          </a>
          <nav className="flex gap-5 text-[0.8rem] text-[#55716a]" aria-label="Main navigation">
            <a className="hover:text-[#174f47]" href="/privacy">Privacy</a>
            <a className="hover:text-[#174f47]" href="/terms">Terms</a>
          </nav>
        </header>
        <article className="legal-copy py-9 sm:py-12">
          <p className="text-[0.68rem] font-bold tracking-[0.08em] text-[#176b61]">INBOXSENSE · LAST UPDATED {content.updated.toUpperCase()}</p>
          <h1 className="mt-3 text-[2rem] font-medium leading-tight text-[#20332e] sm:text-[2.5rem]">{content.title}</h1>
          {content.sections.map((section) => (
            <section key={section.heading}>
              <h2>{section.heading}</h2>
              {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
              {section.bullets && <ul>{section.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}</ul>}
            </section>
          ))}
        </article>
        <footer className="border-t border-[#d9ded8] py-5 text-[0.75rem] text-[#758179]">
          <a className="text-[#55716a] hover:text-[#174f47]" href="/">Back to InboxSense</a>
        </footer>
      </div>
    </main>
  )
}