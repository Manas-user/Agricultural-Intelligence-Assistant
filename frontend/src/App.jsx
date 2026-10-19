import { useEffect, useRef, useState } from 'react'

function App() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Selected language
  const [language, setLanguage] = useState('en-IN')

  // Voice recognition state
  const [isListening, setIsListening] = useState(false)

  const recognitionRef = useRef(null)

  // ---------------------------------------------------------
  // LANGUAGE INFORMATION
  // ---------------------------------------------------------

  const languageNames = {
    'en-IN': 'English',
    'hi-IN': 'Hindi',
    'mr-IN': 'Marathi'
  }

  // ---------------------------------------------------------
  // SEARCH FUNCTION
  // ---------------------------------------------------------

  const handleSearch = async (searchQuery = query) => {
    const finalQuery = searchQuery.trim()

    if (!finalQuery) {
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch('/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: finalQuery,
          language: language
        }),
      })

      let data

      try {
        data = await response.json()
      } catch {
        throw new Error('Invalid response received from server.')
      }

      if (!response.ok) {
        throw new Error(
          data?.error || 'Failed to fetch response from server.'
        )
      }

      setResult(data)

    } catch (err) {
      console.error('Search error:', err)

      setError(
        err.message ||
        'Unable to connect to the server. Please make sure the backend is running.'
      )

    } finally {
      setLoading(false)
    }
  }

  // ---------------------------------------------------------
  // FORM SUBMIT
  // ---------------------------------------------------------

  const handleSubmit = async (e) => {
    e.preventDefault()

    await handleSearch(query)
  }

  // ---------------------------------------------------------
  // SPEECH RECOGNITION
  // ---------------------------------------------------------

  const startVoiceSearch = () => {
    setError(null)

    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition

    if (!SpeechRecognition) {
      setError(
        'Voice search is not supported in this browser. Please use Google Chrome or Microsoft Edge.'
      )
      return
    }

    // If already listening, stop it
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop()
      return
    }

    const recognition = new SpeechRecognition()

    recognitionRef.current = recognition

    // Selected language controls speech recognition language
    recognition.lang = language

    // We only need one spoken query
    recognition.continuous = false

    // Don't show partial speech results
    recognition.interimResults = false

    // Only use the best recognition result
    recognition.maxAlternatives = 1

    // -------------------------------------------------------
    // WHEN SPEECH RECOGNITION STARTS
    // -------------------------------------------------------

    recognition.onstart = () => {
      setIsListening(true)
      setError(null)
    }

    // -------------------------------------------------------
    // WHEN SPEECH IS RECOGNIZED
    // -------------------------------------------------------

    recognition.onresult = async (event) => {
      try {
        const transcript =
          event.results[0][0].transcript.trim()

        if (!transcript) {
          setError('No speech was detected. Please try again.')
          return
        }

        // Put recognized speech into search box
        setQuery(transcript)

        // Automatically search
        await handleSearch(transcript)

      } catch (err) {
        console.error('Speech result error:', err)

        setError(
          'Could not process your voice query. Please try again.'
        )
      }
    }

    // -------------------------------------------------------
    // SPEECH RECOGNITION ERROR
    // -------------------------------------------------------

    recognition.onerror = (event) => {
      console.error(
        'Speech recognition error:',
        event.error
      )

      switch (event.error) {
        case 'not-allowed':
          setError(
            'Microphone permission was denied. Please allow microphone access in your browser.'
          )
          break

        case 'audio-capture':
          setError(
            'No microphone was found. Please check your microphone.'
          )
          break

        case 'no-speech':
          setError(
            'No speech was detected. Please speak clearly and try again.'
          )
          break

        case 'network':
          setError(
            'Speech recognition network error. Please check your internet connection.'
          )
          break

        case 'language-not-supported':
          setError(
            `${languageNames[language]} speech recognition is not supported by your browser.`
          )
          break

        default:
          setError(
            'Voice recognition failed. Please try again.'
          )
      }

      setIsListening(false)
    }

    // -------------------------------------------------------
    // WHEN RECOGNITION ENDS
    // -------------------------------------------------------

    recognition.onend = () => {
      setIsListening(false)
      recognitionRef.current = null
    }

    try {
      recognition.start()
    } catch (err) {
      console.error('Could not start recognition:', err)

      setIsListening(false)
      recognitionRef.current = null

      setError(
        'Could not start microphone. Please try again.'
      )
    }
  }

  // ---------------------------------------------------------
  // STOP VOICE RECOGNITION WHEN COMPONENT UNMOUNTS
  // ---------------------------------------------------------

  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop()
      }
    }
  }, [])

  // ---------------------------------------------------------
  // CHANGE LANGUAGE
  // ---------------------------------------------------------

  const handleLanguageChange = (e) => {
    const newLanguage = e.target.value

    // Stop current voice recognition if language changes
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      recognitionRef.current = null
    }

    setIsListening(false)
    setLanguage(newLanguage)
    setError(null)
  }

  // ---------------------------------------------------------
  // UI
  // ---------------------------------------------------------

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 flex flex-col items-center py-12 px-4 sm:px-6 lg:px-8 font-sans">

      <div className="w-full max-w-3xl space-y-8">

        {/* ==================================================
            HEADER
        ================================================== */}

        <div className="text-center">

          <div className="inline-flex items-center justify-center p-3 bg-emerald-500 rounded-full mb-4 shadow-lg shadow-emerald-500/30">

            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-8 w-8 text-white"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>

          </div>

          <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">
            Agricultural Intelligence{' '}
            <span className="text-emerald-600">
              Assistant
            </span>
          </h1>

          <p className="mt-3 text-lg text-gray-600">
            Ask questions about farming schemes, crop welfare,
            and government policies.
          </p>

        </div>


        {/* ==================================================
            SEARCH BOX
        ================================================== */}

        <div className="bg-white rounded-2xl shadow-xl shadow-emerald-900/5 overflow-hidden">

          {/* LANGUAGE SELECTOR */}

          <div className="px-4 pt-4">

            <label
              htmlFor="language"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Answer & Voice Language
            </label>

            <select
              id="language"
              value={language}
              onChange={handleLanguageChange}
              disabled={loading || isListening}
              className="w-full border border-gray-200 rounded-xl px-4 py-3 text-gray-800 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            >
              <option value="en-IN">
                English
              </option>

              <option value="hi-IN">
                हिंदी
              </option>

              <option value="mr-IN">
                मराठी
              </option>
            </select>

          </div>


          {/* SEARCH FORM */}

          <form
            onSubmit={handleSubmit}
            className="p-4 flex items-center gap-2"
          >

            <div className="relative w-full">

              {/* Search Icon */}

              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">

                <svg
                  className="h-5 w-5 text-gray-400"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z"
                    clipRule="evenodd"
                  />
                </svg>

              </div>


              <input
                type="text"
                className="block w-full pl-11 pr-3 py-4 border-transparent text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-0 focus:border-transparent sm:text-lg bg-transparent"
                placeholder={
                  language === 'hi-IN'
                    ? 'हिंदी में अपना प्रश्न पूछें...'
                    : language === 'mr-IN'
                      ? 'मराठीत तुमचा प्रश्न विचारा...'
                      : 'Ask about farming schemes...'
                }
                value={query}
                onChange={(e) =>
                  setQuery(e.target.value)
                }
                disabled={loading}
              />

            </div>


            {/* MICROPHONE BUTTON */}

            <button
              type="button"
              onClick={startVoiceSearch}
              disabled={loading}
              title={
                isListening
                  ? 'Stop listening'
                  : 'Voice search'
              }
              className={`flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 ${
                isListening
                  ? 'bg-red-500 hover:bg-red-600 text-white animate-pulse'
                  : 'bg-emerald-100 hover:bg-emerald-200 text-emerald-700'
              }`}
            >

              {isListening ? (

                // Stop icon

                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-6 w-6"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                >
                  <rect
                    x="7"
                    y="7"
                    width="10"
                    height="10"
                    rx="1"
                  />
                </svg>

              ) : (

                // Microphone icon

                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 1a3 3 0 00-3 3v7a3 3 0 006 0V4a3 3 0 00-3-3z"
                  />

                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 10v1a7 7 0 01-14 0v-1M12 18v5M8 23h8"
                  />
                </svg>

              )}

            </button>


            {/* SEARCH BUTTON */}

            <button
              type="submit"
              disabled={
                loading ||
                !query.trim() ||
                isListening
              }
              className="flex-shrink-0 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white font-medium py-3 px-6 rounded-xl transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 flex items-center justify-center"
            >

              {loading ? (

                <>
                  <svg
                    className="animate-spin -ml-1 mr-2 h-5 w-5 text-white"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />

                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>

                  Searching...
                </>

              ) : (

                'Search'

              )}

            </button>

          </form>


          {/* VOICE STATUS */}

          {isListening && (
            <div className="px-6 pb-4">

              <div className="rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700 flex items-center">

                <span className="relative flex h-3 w-3 mr-3">

                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>

                  <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>

                </span>

                Listening in{' '}
                <strong className="ml-1">
                  {languageNames[language]}
                </strong>
                ...

              </div>

            </div>
          )}

        </div>


        {/* ==================================================
            ERROR
        ================================================== */}

        {error && (

          <div className="rounded-xl bg-red-50 p-4 border border-red-200">

            <div className="flex">

              <div className="flex-shrink-0">

                <svg
                  className="h-5 w-5 text-red-400"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l-1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>

              </div>

              <div className="ml-3">

                <h3 className="text-sm font-medium text-red-800">
                  Error
                </h3>

                <div className="mt-2 text-sm text-red-700">
                  <p>{error}</p>
                </div>

              </div>

            </div>

          </div>

        )}


        {/* ==================================================
            RESULTS
        ================================================== */}

        {result && (

          <div className="bg-white rounded-2xl shadow-xl shadow-emerald-900/5 overflow-hidden border border-gray-100 transition-all duration-500 ease-in-out opacity-100 translate-y-0">

            {/* ANSWER */}

            <div className="px-6 py-6 sm:px-8 sm:py-8">

              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">

                <h2 className="text-xl font-bold text-gray-900 flex items-center">

                  <svg
                    className="h-6 w-6 text-emerald-500 mr-2"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 10V3L4 14h7v7l9-11h-7z"
                    />
                  </svg>

                  Answer

                </h2>


                <div className="flex gap-2 flex-wrap">

                  {result.answer_language && (

                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">

                      Answer:{' '}
                      {result.answer_language}

                    </span>

                  )}

                  {result.detected_language && (

                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">

                      Query:{' '}
                      {result.detected_language.toUpperCase()}

                    </span>

                  )}

                </div>

              </div>


              <div className="prose prose-emerald max-w-none text-gray-700 leading-relaxed whitespace-pre-wrap">

                {result.answer}

              </div>

            </div>


            {/* SOURCES */}

            {result.sources &&
              result.sources.length > 0 && (

                <div className="bg-gray-50 px-6 py-4 sm:px-8 border-t border-gray-100">

                  <h3 className="text-sm font-semibold text-gray-500 tracking-wider uppercase mb-3 flex items-center">

                    <svg
                      className="h-4 w-4 mr-1.5"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                      />
                    </svg>

                    Source Documents

                  </h3>


                  <ul className="space-y-2">

                    {result.sources.map(
                      (source, index) => {

                        const filename =
                          typeof source === 'string'
                            ? source.split(/[\\/]/).pop()
                            : source?.source ||
                              source?.metadata?.source ||
                              'Source document'

                        return (

                          <li
                            key={index}
                            className="flex items-start"
                          >

                            <span className="flex-shrink-0 h-5 w-5 text-emerald-500 mr-2 flex items-center justify-center">
                              •
                            </span>

                            <span className="text-sm text-gray-600 break-all bg-white px-3 py-1 rounded-md shadow-sm border border-gray-200">

                              {filename}

                            </span>

                          </li>

                        )

                      }
                    )}

                  </ul>

                </div>

              )}

          </div>

        )}

      </div>

    </div>
  )
}

export default App