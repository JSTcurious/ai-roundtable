// Build: 2026-04-25T06:03:55.229486
/**
 * App flow: LandingPage → IntakeFlow → SessionView (incl. TakeFurther).
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

function App() {
  const [screen, setScreen] = useState(SCREENS.LANDING);
  const [intakeMountKey, setIntakeMountKey] = useState(0);
  const [initialIntakeMessage, setInitialIntakeMessage] = useState(null);
  const [sessionConfig, setSessionConfig] = useState(null);

  const handleLandingSubmit = useCallback((text) => {
    setInitialIntakeMessage(text.trim());
    setIntakeMountKey((k) => k + 1);
    setScreen(SCREENS.INTAKE);
  }, []);

  const handleIntakeComplete = useCallback((config) => {
    setSessionConfig(config);
    setScreen(SCREENS.SESSION);
  }, []);

  const handleBackToLanding = useCallback(() => {
    setScreen(SCREENS.LANDING);
    setInitialIntakeMessage(null);
    setSessionConfig(null);
  }, []);

  return (
    <>
      {screen === SCREENS.LANDING && (
        <LandingPage
          onSubmitDescription={handleLandingSubmit}
        />
      )}
      {screen === SCREENS.INTAKE && (
        <IntakeFlow
          key={intakeMountKey}
          initialUserMessage={initialIntakeMessage}
          onComplete={handleIntakeComplete}
          onBack={handleBackToLanding}
        />
      )}
      {screen === SCREENS.SESSION && sessionConfig && (
        <SessionView
          sessionConfig={sessionConfig}
          onSynthesisComplete={() => {}}
          onNavigateHome={handleBackToLanding}
        />
      )}
    </>
  );
}

export default App;
