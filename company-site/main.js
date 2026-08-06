const menuButton = document.querySelector('.menu-button');
const siteNav = document.querySelector('#site-nav');

if (menuButton && siteNav) {
  menuButton.addEventListener('click', () => {
    const expanded = menuButton.getAttribute('aria-expanded') === 'true';
    menuButton.setAttribute('aria-expanded', String(!expanded));
    siteNav.classList.toggle('is-open', !expanded);
  });
}

const scenarios = {
  confirmed: {
    label: 'You meet the published support requirements.',
    status: 'confirmed',
    copy: 'The accepted household-income record is within the threshold set by the active policy release.',
    ruleTitle: 'Income is within the support threshold',
    ruleCopy: 'Annual household income must be at or below R350,000.',
    evidenceTitle: 'Income record accepted',
    evidenceCopy: "The record was reviewed and accepted under the institution's evidence process.",
    evidenceNote: 'Source date: 08 March 2026',
    nextTitle: 'Your institution completes any separate process.',
    nextCopy: 'This explanation does not replace a registration, committee, or payment decision held elsewhere.',
    traceEvidence: 'The income record is accepted and cited to its source.',
    traceResult: 'The active rule is satisfied. A separate institutional decision may still be required.'
  },
  provisional: {
    label: 'Your position is provisional while a record is refreshed.',
    status: 'provisional',
    copy: 'The policy condition appears to be satisfied, but the attendance record used for this example is older than the institution\'s stated freshness window.',
    ruleTitle: 'Attendance record must meet the participation requirement',
    ruleCopy: 'The policy requires the institution to confirm that the recorded participation requirement has been met.',
    evidenceTitle: 'Attendance record is pending refresh',
    evidenceCopy: 'The source is not treated as a confirmed fact until the designated department updates or verifies it.',
    evidenceNote: 'Last source update: 14 February 2026',
    nextTitle: 'Wait for the source update or ask for help early.',
    nextCopy: 'The institution should name the source owner and the next available review route. This page would not silently convert stale data into a final result.',
    traceEvidence: 'The attendance source is present but not current enough to confirm the condition.',
    traceResult: 'The explanation names the uncertainty and its source instead of presenting a final outcome.'
  },
  review: {
    label: 'A review route is available before a final position is confirmed.',
    status: 'review',
    copy: 'A record conflicts with the policy application in this fictional scenario. The system preserves the trace and identifies the right route for a person to examine it.',
    ruleTitle: 'The active policy release applies to this cohort',
    ruleCopy: 'The rule applies to people admitted in the academic period selected by the institution.',
    evidenceTitle: 'Cohort record conflicts with the available source',
    evidenceCopy: 'The discrepancy cannot be resolved by the system alone. A designated institutional reviewer must determine the accepted position.',
    evidenceNote: 'Review required before evaluation',
    nextTitle: 'Request an institutional review.',
    nextCopy: 'The person does not need to know the internal policy language. The review route carries the cited rule and the conflicting record to the responsible team.',
    traceEvidence: 'Two records imply different cohort dates, so neither is silently preferred.',
    traceResult: 'The output is a governed review route, not an invented decision.'
  }
};

const setText = (id, value) => {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
};

document.querySelectorAll('.scenario-button').forEach((button) => {
  button.addEventListener('click', () => {
    const scenario = scenarios[button.dataset.scenario];
    if (!scenario) return;

    document.querySelectorAll('.scenario-button').forEach((item) => item.classList.toggle('is-active', item === button));
    const status = document.getElementById('decision-status');
    if (status) {
      status.className = `status status-${scenario.status}`;
      status.innerHTML = `<span aria-hidden="true"></span><strong>${scenario.label}</strong>`;
    }
    setText('decision-copy', scenario.copy);
    setText('rule-title', scenario.ruleTitle);
    setText('rule-copy', scenario.ruleCopy);
    setText('evidence-title', scenario.evidenceTitle);
    setText('evidence-copy', scenario.evidenceCopy);
    setText('evidence-note', scenario.evidenceNote);
    setText('next-title', scenario.nextTitle);
    setText('next-copy', scenario.nextCopy);
    setText('trace-evidence', scenario.traceEvidence);
    setText('trace-result', scenario.traceResult);
  });
});
