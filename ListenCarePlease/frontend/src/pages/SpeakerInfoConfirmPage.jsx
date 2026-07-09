import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getProcessingStatus, confirmSpeakerInfo } from '../services/api'

export default function SpeakerInfoConfirmPage() {
  const { fileId } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [speakerInfo, setSpeakerInfo] = useState(null)
  const [speakerCount, setSpeakerCount] = useState(0)
  const [detectedNames, setDetectedNames] = useState([])
  const [detectedNicknames, setDetectedNicknames] = useState([])
  const [selectedNames, setSelectedNames] = useState([]) // 선택된 이름들
  const [selectedNicknames, setSelectedNicknames] = useState([]) // 선택된 닉네임들
  const [isEditing, setIsEditing] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchSpeakerInfo()
  }, [fileId])

  const fetchSpeakerInfo = async () => {
    try {
      setLoading(true)
      // 처리 상태에서 화자 정보 가져오기
      const status = await getProcessingStatus(fileId)

      if (status.status !== 'completed') {
        setError('아직 처리가 완료되지 않았습니다.')
        setLoading(false)
        return
      }

      // 화자 수와 감지된 이름, 닉네임 설정
      const count = status.speaker_count || 0
      const names = status.detected_names || []
      const nicknames = status.detected_nicknames || []

      setSpeakerInfo({
        speaker_count: count,
        detected_names: names,
        detected_nicknames: nicknames
      })
      setSpeakerCount(count)
      setDetectedNames(names)
      setDetectedNicknames(nicknames)
      // 초기 선택 상태: 모든 이름과 닉네임 선택
      setSelectedNames([...names])
      setSelectedNicknames([...nicknames])
      setLoading(false)
    } catch (error) {
      console.error('화자 정보 조회 실패:', error)
      setError('화자 정보를 불러올 수 없습니다.')
      setLoading(false)
    }
  }

  const handleAddName = () => {
    setDetectedNames([...detectedNames, ''])
    // 새로 추가된 이름은 선택하지 않음 (빈 값이므로)
  }

  const handleRemoveName = (index) => {
    const nameToRemove = detectedNames[index]
    setDetectedNames(detectedNames.filter((_, i) => i !== index))
    // 선택된 이름 목록에서도 제거
    setSelectedNames(selectedNames.filter(n => n !== nameToRemove))
  }

  const handleNameChange = (index, value) => {
    const updated = [...detectedNames]
    const oldName = updated[index]
    updated[index] = value
    setDetectedNames(updated)
    
    // 선택된 이름 목록도 업데이트
    if (selectedNames.includes(oldName)) {
      setSelectedNames(selectedNames.map(n => n === oldName ? value : n))
    }
  }

  const handleAddNickname = () => {
    setDetectedNicknames([...detectedNicknames, ''])
    // 새로 추가된 닉네임은 선택하지 않음 (빈 값이므로)
  }

  const handleRemoveNickname = (index) => {
    const nicknameToRemove = detectedNicknames[index]
    setDetectedNicknames(detectedNicknames.filter((_, i) => i !== index))
    // 선택된 닉네임 목록에서도 제거
    setSelectedNicknames(selectedNicknames.filter(n => n !== nicknameToRemove))
  }

  const handleNicknameChange = (index, value) => {
    const updated = [...detectedNicknames]
    const oldNickname = updated[index]
    updated[index] = value
    setDetectedNicknames(updated)
    
    // 선택된 닉네임 목록도 업데이트
    if (selectedNicknames.includes(oldNickname)) {
      setSelectedNicknames(selectedNicknames.map(n => n === oldNickname ? value : n))
    }
  }

  const handleNameToggle = (name) => {
    if (selectedNames.includes(name)) {
      setSelectedNames(selectedNames.filter(n => n !== name))
    } else {
      setSelectedNames([...selectedNames, name])
    }
  }

  const handleNicknameToggle = (nickname) => {
    if (selectedNicknames.includes(nickname)) {
      setSelectedNicknames(selectedNicknames.filter(n => n !== nickname))
    } else {
      setSelectedNicknames([...selectedNicknames, nickname])
    }
  }

  const handleConfirm = async () => {
    try {
      setLoading(true)

      // 선택된 이름/닉네임만 사용 (빈 값 제거)
      const validNames = selectedNames.filter(name => name.trim() !== '')
      const validNicknames = selectedNicknames.filter(nickname => nickname.trim() !== '')

      // DB에 사용자 확정 정보 저장
      await confirmSpeakerInfo(fileId, speakerCount, validNames, validNicknames)

      // 화자 정보를 다음 페이지로 전달
      navigate(`/analyzing/${fileId}`, {
        state: {
          speakerCount,
          detectedNames: validNames
        }
      })
    } catch (error) {
      console.error('화자 정보 저장 실패:', error)
      const errorMessage = error.response?.data?.detail || error.message || '화자 정보를 저장하는 중 오류가 발생했습니다.'
      setError(errorMessage)
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-accent-blue mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-300">화자 정보를 불러오는 중...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="text-center">
          <div className="text-red-600 dark:text-red-400 text-6xl mb-4">⚠️</div>
          <p className="text-xl text-gray-700 dark:text-gray-300 mb-4">{error}</p>
          <button
            onClick={() => navigate(`/processing/${fileId}`)}
            className="px-6 py-3 bg-accent-blue text-white rounded-xl font-semibold hover:bg-blue-600 transition-colors"
          >
            처리 페이지로 돌아가기
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="max-w-3xl mx-auto">
        {/* 헤더 */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            화자 정보 확인
          </h1>
          <p className="text-gray-600 dark:text-gray-300">
            시스템이 분석한 화자 정보를 확인해주세요
          </p>
        </div>

        {/* 메인 카드 */}
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-2xl shadow-xl p-8 mb-6 border border-bg-accent/30">
          {/* 화자 수 섹션 */}
          <div className="mb-8 pb-8 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                🎤 화자 수
              </h2>
              {!isEditing && (
                <button
                  onClick={() => setIsEditing(true)}
                  className="text-sm text-accent-blue hover:text-blue-600 font-medium"
                >
                  수정하기
                </button>
              )}
            </div>

            <div className="flex items-center gap-4">
              {isEditing ? (
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={speakerCount}
                    onChange={(e) => setSpeakerCount(parseInt(e.target.value) || 1)}
                    className="w-20 px-3 py-2 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg focus:ring-2 focus:ring-accent-blue focus:border-transparent text-gray-900 dark:text-white"
                  />
                  <span className="text-gray-700 dark:text-gray-300">명</span>
                </div>
              ) : (
                <div className="text-4xl font-bold text-accent-blue">
                  {speakerCount}명
                </div>
              )}
            </div>

            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              대화에 참여한 화자의 수입니다
            </p>
          </div>

          {/* 감지된 이름 섹션 */}
          <div className="mb-8 pb-8 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                👥 감지된 이름
              </h2>
              {isEditing && (
                <button
                  onClick={handleAddName}
                  className="text-sm text-accent-blue hover:text-blue-600 font-medium"
                >
                  + 이름 추가
                </button>
              )}
            </div>

            <div className="space-y-3">
              {detectedNames.length === 0 ? (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                  <p>감지된 이름이 없습니다</p>
                  <p className="text-sm mt-1">대화에서 이름이 언급되지 않았을 수 있습니다</p>
                  {isEditing && (
                    <button
                      onClick={handleAddName}
                      className="mt-4 px-4 py-2 bg-accent-blue text-white rounded-lg hover:bg-blue-600"
                    >
                      이름 추가하기
                    </button>
                  )}
                </div>
              ) : (
                detectedNames.map((name, index) => (
                  <div key={index} className="flex items-center gap-3">
                    {isEditing ? (
                      <>
                        <input
                          type="checkbox"
                          checked={selectedNames.includes(name)}
                          onChange={() => handleNameToggle(name)}
                          className="w-5 h-5 text-accent-blue border-gray-300 rounded focus:ring-accent-blue"
                        />
                        <input
                          type="text"
                          value={name}
                          onChange={(e) => handleNameChange(index, e.target.value)}
                          placeholder="이름 입력"
                          className="flex-1 px-4 py-2 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg focus:ring-2 focus:ring-accent-blue focus:border-transparent text-gray-900 dark:text-white"
                        />
                        <button
                          onClick={() => handleRemoveName(index)}
                          className="px-3 py-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                        >
                          삭제
                        </button>
                      </>
                    ) : (
                      <>
                        <input
                          type="checkbox"
                          checked={selectedNames.includes(name)}
                          onChange={() => handleNameToggle(name)}
                          className="w-5 h-5 text-accent-blue border-gray-300 rounded focus:ring-accent-blue"
                        />
                        <div className="flex-1 px-4 py-2 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg font-medium">
                          {name}
                        </div>
                      </>
                    )}
                  </div>
                ))
              )}
            </div>

            <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">
              💡 대화에서 언급된 이름들입니다. 수정이 필요하면 위의 "수정하기" 버튼을 클릭하세요.
            </p>
          </div>

          {/* 감지된 닉네임 섹션 */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                🏷️ 감지된 닉네임
              </h2>
              {isEditing && (
                <button
                  onClick={handleAddNickname}
                  className="text-sm text-accent-blue hover:text-blue-600 font-medium"
                >
                  + 닉네임 추가
                </button>
              )}
            </div>

            <div className="space-y-3">
              {detectedNicknames.length === 0 ? (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                  <p>감지된 닉네임이 없습니다</p>
                  <p className="text-sm mt-1">대화에서 역할이나 특징이 명확하지 않을 수 있습니다</p>
                  {isEditing && (
                    <button
                      onClick={handleAddNickname}
                      className="mt-4 px-4 py-2 bg-accent-blue text-white rounded-lg hover:bg-blue-600"
                    >
                      닉네임 추가하기
                    </button>
                  )}
                </div>
              ) : (
                detectedNicknames.map((nickname, index) => (
                  <div key={index} className="flex items-center gap-3">
                    {isEditing ? (
                      <>
                        <input
                          type="checkbox"
                          checked={selectedNicknames.includes(nickname)}
                          onChange={() => handleNicknameToggle(nickname)}
                          className="w-5 h-5 text-accent-blue border-gray-300 rounded focus:ring-accent-blue"
                        />
                        <input
                          type="text"
                          value={nickname}
                          onChange={(e) => handleNicknameChange(index, e.target.value)}
                          placeholder="닉네임 입력"
                          className="flex-1 px-4 py-2 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg focus:ring-2 focus:ring-accent-blue focus:border-transparent text-gray-900 dark:text-white"
                        />
                        <button
                          onClick={() => handleRemoveNickname(index)}
                          className="px-3 py-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                        >
                          삭제
                        </button>
                      </>
                    ) : (
                      <>
                        <input
                          type="checkbox"
                          checked={selectedNicknames.includes(nickname)}
                          onChange={() => handleNicknameToggle(nickname)}
                          className="w-5 h-5 text-accent-blue border-gray-300 rounded focus:ring-accent-blue"
                        />
                        <div className="flex-1 px-4 py-2 bg-orange-50 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 rounded-lg font-medium">
                          {nickname}
                        </div>
                      </>
                    )}
                  </div>
                ))
              )}
            </div>

            <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">
              💡 시스템이 분석한 화자별 역할이나 특징입니다. 수정이 필요하면 위의 "수정하기" 버튼을 클릭하세요.
            </p>
          </div>
        </div>

        {/* 액션 버튼 */}
        <div className="flex gap-4">
          {isEditing ? (
            <>
              <button
                onClick={() => {
                  // 원래 값으로 복구
                  setSpeakerCount(speakerInfo.speaker_count)
                  setDetectedNames(speakerInfo.detected_names)
                  setDetectedNicknames(speakerInfo.detected_nicknames || [])
                  setSelectedNames([...speakerInfo.detected_names])
                  setSelectedNicknames([...speakerInfo.detected_nicknames || []])
                  setIsEditing(false)
                }}
                className="flex-1 px-6 py-3 bg-bg-secondary dark:bg-bg-secondary-dark text-gray-700 dark:text-gray-300 rounded-xl font-semibold hover:bg-bg-accent/20 transition-colors"
              >
                취소
              </button>
              <button
                onClick={() => {
                  // 수정 완료
                  setIsEditing(false)
                }}
                className="flex-1 px-6 py-3 bg-accent-blue text-white rounded-xl font-semibold hover:bg-blue-600 transition-colors shadow-lg"
              >
                저장
              </button>
            </>
          ) : (
            <button
              onClick={handleConfirm}
              className="w-full px-6 py-4 bg-accent-blue text-white rounded-xl font-semibold hover:bg-blue-600 transition-all shadow-lg text-lg"
            >
              확인 완료 → 화자 태깅하기
            </button>
          )}
        </div>

        {/* 안내 메시지 */}
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <p className="text-sm text-blue-800 dark:text-blue-300">
            ℹ️ 다음 단계에서는 각 화자(SPEAKER_00, SPEAKER_01...)에게 실제 이름을 매핑합니다.
          </p>
        </div>

        {/* 홈으로 가기 버튼 */}
        <div className="mt-6 text-center">
          <button
            onClick={() => navigate('/')}
            className="px-6 py-2 bg-bg-secondary dark:bg-bg-secondary-dark hover:bg-bg-accent/20 text-gray-700 dark:text-gray-200 rounded-lg font-medium transition"
          >
            홈으로 가기
          </button>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            나중에 대시보드에서 이어서 진행할 수 있습니다
          </p>
        </div>
      </div>
    </div>
  )
}
