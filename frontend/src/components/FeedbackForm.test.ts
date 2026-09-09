import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/en.json'

vi.mock('@/api/feedback', () => ({
  postFeedback: vi.fn(),
}))
vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, get: vi.fn() }
})

import { postFeedback } from '@/api/feedback'
import { ApiResponseError, get } from '@/api/client'
import FeedbackForm from './FeedbackForm.vue'

const postFeedbackMock = vi.mocked(postFeedback)
const getMock = vi.mocked(get)

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

function mountForm(props: { sessionId?: string; fipId?: string }) {
  return mount(FeedbackForm, { props, global: { plugins: [makeI18n()] } })
}

async function answerAllQuestions(wrapper: Awaited<ReturnType<typeof mountForm>>, value = 4) {
  const fieldsets = wrapper.findAll('.likert')
  expect(fieldsets).toHaveLength(3)
  for (const fieldset of fieldsets) {
    const radios = fieldset.findAll('input[type="radio"]')
    expect(radios).toHaveLength(5)
    await radios[value - 1].setValue()
  }
}

// Criterion 17 (docs/specs/05-v1-completion.md §8): posts once and stays
// hidden (thanks state) on reload of the same device.
describe('FeedbackForm.vue — once per browser', () => {
  beforeEach(() => {
    localStorage.clear()
    postFeedbackMock.mockReset()
    getMock.mockReset()
    getMock.mockResolvedValue({ status: 'ok' })
  })

  it('submits the three Likert answers and the comment, then shows thanks and sets the localStorage flag', async () => {
    postFeedbackMock.mockResolvedValue({ status: 'recorded' })
    const wrapper = mountForm({ fipId: 'fip-1' })
    await flushPromises()

    await answerAllQuestions(wrapper, 4)
    await wrapper.get('textarea').setValue('Great tool')

    const submitBtn = wrapper.get('button.btn-primary')
    expect(submitBtn.attributes('disabled')).toBeUndefined()
    await submitBtn.trigger('click')
    await flushPromises()

    expect(postFeedbackMock).toHaveBeenCalledWith(
      expect.objectContaining({ q1: 4, q2: 4, q3: 4, comment: 'Great tool', fipId: 'fip-1' })
    )
    expect(wrapper.text()).toContain(en.feedback.thanks)
    expect(localStorage.getItem('fipm.feedback.fip-1')).toBe('done')
  })

  it('the submit button stays disabled until all three questions are answered', async () => {
    const wrapper = mountForm({ fipId: 'fip-1' })
    await flushPromises()
    const submitBtn = wrapper.get('button.btn-primary')
    expect(submitBtn.attributes('disabled')).toBeDefined()

    const fieldsets = wrapper.findAll('.likert')
    await fieldsets[0].findAll('input[type="radio"]')[0].setValue()
    await fieldsets[1].findAll('input[type="radio"]')[0].setValue()
    expect(wrapper.get('button.btn-primary').attributes('disabled')).toBeDefined()

    await fieldsets[2].findAll('input[type="radio"]')[0].setValue()
    expect(wrapper.get('button.btn-primary').attributes('disabled')).toBeUndefined()
  })

  it('stays hidden behind the thanks state on a fresh mount once this browser already submitted for this fip', async () => {
    localStorage.setItem('fipm.feedback.fip-1', 'done')
    const wrapper = mountForm({ fipId: 'fip-1' })
    await flushPromises()

    expect(wrapper.text()).toContain(en.feedback.thanks)
    expect(wrapper.find('input[type="radio"]').exists()).toBe(false)
    expect(postFeedbackMock).not.toHaveBeenCalled()
  })

  it('keys the localStorage flag by sessionId when both sessionId and fipId are absent from the other prop', async () => {
    postFeedbackMock.mockResolvedValue({ status: 'recorded' })
    const wrapper = mountForm({ sessionId: 'session-1' })
    await flushPromises()
    await answerAllQuestions(wrapper, 5)
    await wrapper.get('button.btn-primary').trigger('click')
    await flushPromises()

    expect(localStorage.getItem('fipm.feedback.session-1')).toBe('done')
  })

  it('hides the form entirely on a 403 feedback_disabled response', async () => {
    postFeedbackMock.mockRejectedValue(new ApiResponseError(403, { detail: 'feedback_disabled' }))
    const wrapper = mountForm({ fipId: 'fip-2' })
    await flushPromises()

    await answerAllQuestions(wrapper, 3)
    await wrapper.get('button.btn-primary').trigger('click')
    await flushPromises()

    expect(wrapper.find('.feedback-form').exists()).toBe(false)
    expect(localStorage.getItem('fipm.feedback.fip-2')).not.toBe('done')
  })

  it('hides the form when GET /api/health reports feedbackEnabled: false', async () => {
    getMock.mockResolvedValue({ status: 'ok', feedbackEnabled: false })
    const wrapper = mountForm({ fipId: 'fip-3' })
    await flushPromises()

    expect(wrapper.find('.feedback-form').exists()).toBe(false)
  })
})
