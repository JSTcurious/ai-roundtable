/**
 * App flow: LandingPage → IntakeFlow → SessionView (incl. TakeFurther).
 * Resume: Landing .json → SessionView (read-only + export).
 */

import React, { useCallback, useState } from "react";
import LandingPage from "./components/LandingPage";
import IntakeFlow from "./components/IntakeFlow";
import SessionView from "./components/SessionView";

const SCREENS = {
  LANDING: "landing",
  INTAKE: "intake",
  SESSION: "session",
};

/** Landing "use as-is" path — skip intake, go straight to SessionView. */
function buildDirectSessionConfig(userInput, tier = "smart") {
  return {
    optimized_prompt: userInput,
    session_title: userInput,
    output_type: "general",
    tier,
    intake_summary: "Direct question — no intake conducted",
    open_assumptions: ["No intake conducted — output based on question as typed"],
  };
}

function App() {
  const [screen, setScreen] = useState(SCREENS.LANDING);
  const [intakeMountKey, setIntakeMountKey] = useState(0);
  const [initialIntakeMessage, setInitialIntakeMessage] = useState(null);
  const [sessionConfig, setSessionConfig] = useState(null);
  const [resumeTranscript, setResumeTranscript] = useState(null);

  const handleLandingSubmit = useCallback((text) => {
    setInitialIntakeMessage(text.trim());
    setResumeTranscript(null);
    setIntakeMountKey((k) => k + 1);
    setScreen(SCREENS.INTAKE);
  }, []);

  const handleDirectSession = useCallback((text, tier = "smart") => {
    const t = text.trim();
    if (!t) return;
    setSessionConfig(buildDirectSessionConfig(t, tier));
    setResumeTranscript(null);
    setInitialIntakeMessage(null);
    setScreen(SCREENS.SESSION);
  }, []);

  const handleResumeSession = useCallback(({ session_config, transcript }) => {
    setSessionConfig(session_config);
    setResumeTranscript(transcript);
    setInitialIntakeMessage(null);
    setScreen(SCREENS.SESSION);
  }, []);

  const handleIntakeComplete = useCallback((config) => {
    setSessionConfig(config);
    setResumeTranscript(null);
    setScreen(SCREENS.SESSION);
  }, []);

  const handleBackToLanding = useCallback(() => {
    setScreen(SCREENS.LANDING);
    setInitialIntakeMessage(null);
    setSessionConfig(null);
    setResumeTranscript(null);
  }, []);

  return (
    <>
      {screen === SCREENS.LANDING && (
        <LandingPage
          onSubmitDescription={handleLandingSubmit}
          onDirectSession={handleDirectSession}
          onResumeSession={handleResumeSession}
        />
      )}
      {screen === SCREENS.INTAKE && (
        <IntakeFlow
          key={intakeMountKey}
          initialUserMessage={initialIntakeMessage}
          selectedUseCase={null}
          onComplete={handleIntakeComplete}
          onBack={handleBackToLanding}
        />
      )}
      {screen === SCREENS.SESSION && sessionConfig && (
        <SessionView
          sessionConfig={sessionConfig}
          resumeTranscript={resumeTranscript}
          onSynthesisComplete={() => {}}
          onNavigateHome={handleBackToLanding}
        />
      )}
    </>
  );
}

export default App;
