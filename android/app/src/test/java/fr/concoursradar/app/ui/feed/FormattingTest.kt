package fr.concoursradar.app.ui.feed

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate

class FormattingTest {
    private val today = LocalDate.of(2026, 11, 27)

    @Test
    fun `deadline labels`() {
        assertNull(deadlineLabel(null, today))
        assertNull(deadlineLabel(today.minusDays(1), today))
        assertEquals(DeadlineLabel.Today, deadlineLabel(today, today))
        assertEquals(DeadlineLabel.Tomorrow, deadlineLabel(today.plusDays(1), today))
        assertEquals(DeadlineLabel.On(LocalDate.of(2026, 12, 6)), deadlineLabel(LocalDate.of(2026, 12, 6), today))
    }

    @Test
    fun `short french dates show the year only when it differs`() {
        assertEquals("6 déc.", shortDate(LocalDate.of(2026, 12, 6), today))
        assertEquals("5 janv. 2027", shortDate(LocalDate.of(2027, 1, 5), today))
    }

    @Test
    fun `every category slug has an emoji`() {
        assertEquals("🎁", categoryEmoji(null))
        assertEquals("📚", categoryEmoji("livres"))
    }
}
